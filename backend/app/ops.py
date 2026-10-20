"""Operations desk: the flood week run by hand, one day at a time.

Unlike Live Operations (which replays every tweet on a clock), nothing happens
here until the operator does it:

  1. supply    pick today's stock for the 19 relief centres from simulated
               options (no new supply, small / standard / large convoy, damaged
               warehouses), and optionally edit any centre's numbers.
  2. reports   add crisis reports from the dataset (the 449 located, actionable
               HumAID tweets of 18-24 Aug 2018) or type a new one. A dataset
               report moves the planner's estimate of that district's need halfway
               to the true need (the Step 6 rule); a typed report adds the people
               it mentions as new need (as in Live Operations).
  3. dispatch  up to four waves a day (06:00, 12:00, 18:00, 24:00). Each wave is
               planned by the chosen strategy (MAPPO with the fairness reward, or the
               fair LP with rationing) with the stock, trucks and estimate at that
               moment, and becomes one operation per centre -> district trip.
  4. outcomes  every operation's team reports success or failure. Success counts as
               delivered; on failure the goods go back to the centre and the need
               stays open, so the next wave plans it again.
  5. close     the day report: need met against the true need, fairness, operations
               and failures. Leftover stock carries over to the next day.

Everything the operator does (supply choice, reports, operations, outcomes, day
reports) is written to the ops_* tables, so the logs survive the session.
"""
import csv
import html
import math
import random
import threading
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta

import networkx as nx

from ml.env.metrics import episode_metrics, gini
from ml.env.relief_env import CONSUMABLES, PROC, RESOURCES, SEVERITY_START_DAY, TRIPS_PER_VEHICLE, TRUCKLOAD
from ml.marl.scenarios import ScenarioEnv
from ml.realloc.loop import (FORECAST_SD, REPORT_PULL, RESOURCE_MAP, WAVES, LPPlanner, MappoPlanner,
                             apply_road_event, travel_from)
from backend.app import live
from backend.app.sim import summarise

POLICIES = {"mappo": "AI agents (MAPPO + fairness)", "lp_rationed": "Optimiser (LP fair + rationing)"}
# Today's supply options. "add" is a share of each centre's starting stock arriving by convoy this
# morning; "keep" scales what the centres still hold (warehouse damage).
SUPPLY_OPTIONS = [
    {"key": "none", "label": "No new supply", "add": 0.0, "keep": 1.0,
     "detail": "Centres work with what is left from yesterday (day 1: the simulated starting stock)."},
    {"key": "small", "label": "Small convoy", "add": 0.10, "keep": 1.0,
     "detail": "Every centre receives 10% of its starting stock."},
    {"key": "standard", "label": "Standard convoy", "add": 0.25, "keep": 1.0,
     "detail": "Every centre receives 25% of its starting stock."},
    {"key": "large", "label": "Large convoy", "add": 0.50, "keep": 1.0,
     "detail": "Every centre receives 50% of its starting stock."},
    {"key": "damaged", "label": "Warehouses flooded", "add": 0.0, "keep": 0.7,
     "detail": "Flood water spoils 30% of what the centres hold."},
]
FAIL_REASONS = ["Road impassable", "Area flooded / no access", "Vehicle breakdown", "Wrong or unclear location",
                "Supplies damaged", "Team diverted to another emergency", "No report from team", "Other"]
IST = timedelta(hours=5, minutes=30)


def _hhmm(h):
    return live._hhmm(h)


def dataset_reports():
    """The located, actionable crisis tweets of the flood week, per scenario day (the Step 6 set)."""
    start = datetime.strptime(SEVERITY_START_DAY, "%Y-%m-%d")
    out = defaultdict(list)
    with open(PROC / "crisis_reports.csv", newline="", encoding="utf8") as f:
        for r in csv.DictReader(f):
            if r["actionable"] != "1" or not r["primary_district"]:
                continue
            t = datetime.strptime(r["posted_utc"], "%Y-%m-%d %H:%M:%S") + IST
            day = (t.date() - start.date()).days + 1
            if 1 <= day <= 7:
                needs = [k for k in r["resources"].split("|") if k]
                res = sorted({x for k in needs for x in RESOURCE_MAP.get(k, [])}) or list(RESOURCES)
                out[day].append({"tweet_id": r["tweet_id"], "day": day, "time": t.strftime("%H:%M"),
                                 "district": r["primary_district"], "category": r["pred_label"],
                                 "confidence": float(r["pred_confidence"]), "urgency": float(r["urgency"]),
                                 "needs": needs, "resources": res, "text": html.unescape(r["text"])})
    return {d: sorted(v, key=lambda x: x["time"]) for d, v in out.items()}


_REPORTS = None


def reports_for(day):
    global _REPORTS
    if _REPORTS is None:
        _REPORTS = dataset_reports()
    return _REPORTS.get(day, [])


class OpsSession:
    def __init__(self, policy="mappo"):
        self.id = uuid.uuid4().hex[:8]
        self.policy = policy
        self.lock = threading.Lock()
        self.env = ScenarioEnv()
        self.obs = self.env.reset(None)
        self.planner = MappoPlanner(self.env) if policy == "mappo" else LPPlanner()
        self.start_stock = {c: dict(s) for c, s in self.env.initial_stock.items()}
        self.base_vehicles = {c["centre_id"]: int(c["vehicles"]) for c in self.env.centres}
        self.names = {c["centre_id"]: c["name"] for c in self.env.centres}
        self.home = {c["centre_id"]: c["district"] for c in self.env.centres}
        self.stock = {c: dict(s) for c, s in self.env.stock.items()}     # carried over day to day
        self.env.stock = self.stock
        self.roads = {int(e["edge_id"]): ("open", float(e["travel_time_hr"])) for e in self.env.edges}
        self.base_tt = {k: t for k, (_, t) in self.roads.items()}
        self.frng = random.Random(499)
        self.orng = random.Random(2024)
        self.events, self.seq = [], 0
        self.operations = []
        self.day_reports = []
        self.done = False
        self._start_day()

    # ---------------------------------------------------------------- day
    def _start_day(self):
        self.day = self.env.day
        for e in self.env.events.get(self.day, []):          # today's road changes are known in the morning
            apply_road_event(self.env, self.roads, e)
        self.travel = travel_from(self.env, self.roads)
        self.truth = {d: dict(v) for d, v in self.env.demand[self.day].items()}
        self.est = {d: {r: v[r] * math.exp(self.frng.gauss(0, FORECAST_SD)) for r in RESOURCES}
                    for d, v in self.truth.items()}
        self.forecast = {d: dict(v) for d, v in self.est.items()}
        self.phase = "supply"
        self.supply = None
        self.vehicles = dict(self.base_vehicles)
        self.used_reports = set()
        self.reports_in = []
        self.sent = defaultdict(float)          # dispatched and not failed
        self.delivered = defaultdict(float)     # confirmed by a success report
        self.teams_used = defaultdict(float)
        self.wave_i = 0
        self.budget = None
        self.plan = {}
        blocked = [e for e, (s, _) in self.roads.items() if s == "blocked"]
        self._log("day", "", f"Day {self.day} starts: {len(blocked)} road links blocked. Choose today's supply.")

    def supply_options(self):
        """Per option, every centre's stock for today if that option is chosen."""
        out = []
        for o in SUPPLY_OPTIONS:
            centres = {}
            for c, s in self.stock.items():
                row = {r: round(s[r] * o["keep"] + self.start_stock[c][r] * o["add"], 1) for r in CONSUMABLES}
                row["rescue_teams"] = s["rescue_teams"]
                row["vehicles"] = self.base_vehicles[c]
                centres[c] = row
            totals = {r: round(sum(v[r] for v in centres.values()), 1) for r in RESOURCES + ["vehicles"]}
            out.append({**{k: o[k] for k in ("key", "label", "detail")}, "centres": centres, "totals": totals})
        return out

    def set_supply(self, key, overrides=None):
        with self.lock:
            if self.done:
                raise ValueError("the week is over; start a new session")
            if self.wave_i > 0:
                raise ValueError("supply is fixed once the first wave has left; close the day to choose again")
            opt = next((o for o in self.supply_options() if o["key"] == key), None)
            if opt is None:
                raise KeyError(f"unknown supply option {key}")
            if self.supply is not None:          # choosing again: start from yesterday's leftovers
                self.stock.update({c: dict(s) for c, s in self._base_stock.items()})
            self._base_stock = {c: dict(s) for c, s in self.stock.items()}
            edited = []
            for c, row in opt["centres"].items():
                row = dict(row)
                for k, v in (overrides or {}).get(c, {}).items():
                    if k in row and v is not None and v >= 0 and abs(v - row[k]) > 1e-9:
                        row[k] = float(v)
                        edited.append(c)
                self.stock[c].update({r: float(row[r]) for r in RESOURCES})
                self.vehicles[c] = int(row["vehicles"])
            self.supply = {"key": key, "label": opt["label"], "edited_centres": sorted(set(edited)),
                           "totals": {r: round(sum(s[r] for s in self.stock.values()), 1) for r in RESOURCES}}
            self.budget = self.planner.budget(self._obs(self.est))
            self.phase = "operate"
            self.plan = self._plan(commit=False)
            e = self._log("supply", "", f"Supply: {opt['label']}" +
                          (f", edited by hand for {len(set(edited))} centres" if edited else ""), supply=self.supply)
            return e

    def _obs(self, demand):
        trucks = {c: v * TRIPS_PER_VEHICLE for c, v in self.vehicles.items()}
        return {**self.env.observe(), "demand": demand, "travel": self.travel, "trucks": trucks,
                "stock": {c: dict(s) for c, s in self.stock.items()}}

    def _plan(self, commit):
        """Plan the next wave with what is known now; commit=True sends it."""
        budget = self.budget if commit else {c: dict(v) for c, v in self.budget.items()}
        stock = self.stock if commit else {c: dict(v) for c, v in self.stock.items()}
        teams = self.teams_used if commit else defaultdict(float, self.teams_used)
        remaining = {d: {r: max(0.0, self.est[d][r] - self.sent[d, r]) for r in RESOURCES} for d in self.est}
        waves_left = len(WAVES) - self.wave_i
        obs = self._obs(remaining)
        obs["trucks"] = {c: v * TRIPS_PER_VEHICLE / len(WAVES) for c, v in self.vehicles.items()}
        obs["stock"] = {c: {**{r: stock[c][r] for r in CONSUMABLES}, "rescue_teams": stock[c]["rescue_teams"] - teams[c]}
                        for c in stock}
        raw = self.planner.allocate(obs, budget) if waves_left > 0 else {}
        out = {}
        for (c, d, r), amt in raw.items():
            amt = float(amt)
            if self.travel.get((c, d)) is None or amt <= 0:
                continue
            if r == "rescue_teams":
                amt = float(min(amt, stock[c][r] - teams[c])); teams[c] += amt
            else:
                amt = float(min(amt, budget[c][r], stock[c][r]))
                budget[c][r] -= amt; stock[c][r] -= amt
            if amt > 1e-6:
                out[(c, d, r)] = amt
                if commit:
                    self.sent[d, r] += amt
        return out

    # ------------------------------------------------------------ reports
    def add_report(self, tweet_id=None, text=None, district=None):
        with self.lock:
            self._need_operating()
            if tweet_id:
                rep = next((x for x in reports_for(self.day) if x["tweet_id"] == tweet_id), None)
                if rep is None:
                    raise KeyError("that report is not in today's dataset reports")
                if tweet_id in self.used_reports:
                    raise ValueError("this report was already added today")
                self.used_reports.add(tweet_id)
                d = rep["district"]
                before = {r: self.est[d][r] for r in RESOURCES}
                for r in rep["resources"]:
                    self.est[d][r] += REPORT_PULL * (self.truth[d][r] - self.est[d][r])
                change = {r: round(self.est[d][r] - before[r], 1) for r in rep["resources"]
                          if abs(self.est[d][r] - before[r]) > 1e-6}
                info = {"source": "dataset", "tweet_id": tweet_id, "district": d, "text": rep["text"],
                        "category": rep["category"], "confidence": rep["confidence"], "urgency": rep["urgency"],
                        "needs": rep["needs"], "posted": rep["time"], "estimate_change": change}
            else:
                a = live.analyse(text, district)
                d = a["district"]
                info = {"source": "typed", "text": text, **{k: a[k] for k in ("category", "confidence", "urgency", "needs")},
                        "district": d}
                if d is None or not a["actionable"]:
                    info["outcome"] = ("not placed: no Kerala place name found; choose a district" if d is None
                                       else "not actionable: no need found, so the plan is unchanged")
                    e = self._log("report", d or "", text, report=info)
                    self.reports_in.append(info | {"seq": e["seq"]})
                    return {"report": info, "replan": None}
                resources = sorted({x for k in a["needs"] for x in RESOURCE_MAP.get(k, [])}) or list(CONSUMABLES)
                people = a["people"] or int(50 + 450 * a["urgency"])
                change = {}
                for r in resources:
                    extra = people * live.PER_PERSON[r] if r in live.PER_PERSON else max(1.0, round(people / 500))
                    self.truth[d][r] += extra
                    self.est[d][r] = max(self.est[d][r], self.sent[d, r]) + extra
                    change[r] = round(extra, 1)
                info |= {"people": people, "people_source": "text" if a["people"] else "urgency",
                         "estimate_change": change, "released": self._release(d, change)}
            info["outcome"] = "need estimate updated, next wave re-planned"
            replan = self._replan()
            e = self._log("report", d, info["text"][:200], report=info, replan=replan)
            self.reports_in.append(info | {"seq": e["seq"]})
            return {"report": info, "replan": replan}

    def _release(self, d, added):
        """Typed reports add need after the day's budget was fixed: nearby centres release reserve."""
        released = {}
        reach = sorted((c for c in self.stock if self.travel.get((c, d)) is not None), key=lambda c: self.travel[(c, d)])
        for r, extra in added.items():
            if r not in CONSUMABLES:
                continue
            left = extra
            for c in reach:
                take = max(0.0, min(left, self.stock[c][r] - self.budget[c][r]))
                self.budget[c][r] += take
                left -= take
                if left <= 1e-6:
                    break
            released[r] = round(extra - left, 1)
        return released

    def _replan(self):
        old, self.plan = self.plan, self._plan(commit=False)
        changes = []
        for k in set(old) | set(self.plan):
            a, b = old.get(k, 0.0), self.plan.get(k, 0.0)
            if abs(b - a) >= live.MIN_CHANGE[k[2]]:
                changes.append({"centre": k[0], "district": k[1], "resource": k[2], "before": round(a, 1), "after": round(b, 1)})
        changes.sort(key=lambda x: -abs(x["after"] - x["before"]) / live.MIN_CHANGE[x["resource"]])
        return {"changes": changes[:12], "n_changes": len(changes)}

    # ----------------------------------------------------------- dispatch
    def _path(self, c, d):
        src = self.home[c]
        if src == d:
            return [d], []
        G = nx.Graph()
        for e in self.env.edges:
            s, tt = self.roads[int(e["edge_id"])]
            if s == "open":
                G.add_edge(e["source"], e["target"], weight=tt, edge_id=int(e["edge_id"]),
                           slowed=tt > self.base_tt[int(e["edge_id"])] + 1e-6)
        path = nx.dijkstra_path(G, src, d, weight="weight")
        legs = [{"from": a, "to": b, "hours": round(G[a][b]["weight"], 2), "slowed": G[a][b]["slowed"],
                 "edge_id": G[a][b]["edge_id"]} for a, b in zip(path, path[1:])]
        return path, legs

    def dispatch(self):
        with self.lock:
            self._need_operating()
            if self.wave_i >= len(WAVES):
                raise ValueError("all four waves have left today; close the day")
            hour = WAVES[self.wave_i]
            sent = self._plan(commit=True)
            # One operation per district per wave: the convoy of everything sent there, from every
            # centre that contributes. Its team reports one outcome for the whole convoy.
            convoys = defaultdict(lambda: defaultdict(dict))
            for (c, d, r), amt in sent.items():
                convoys[d][c][r] = round(amt, 1)
            new = []
            for d, by_centre in sorted(convoys.items(), key=lambda kv: -self.env.severity.get(self.day, {}).get(kv[0], 0)):
                sources = []
                for c, items in sorted(by_centre.items(), key=lambda kv: self.travel[(kv[0], d)]):
                    path, legs = self._path(c, d)
                    sources.append({"centre": c, "centre_name": self.names[c], "items": items,
                                    "hours": round(self.travel[(c, d)], 2), "path": path, "legs": legs})
                items = defaultdict(float)
                for x in sources:
                    for r, a in x["items"].items():
                        items[r] += a
                op = {"op_id": f"D{self.day}-W{self.wave_i + 1}-{len(new) + 1:02d}", "day": self.day,
                      "wave": _hhmm(hour), "district": d, "items": {r: round(a, 1) for r, a in items.items()},
                      "sources": sources, "centres": [x["centre"] for x in sources],
                      "hours": max(x["hours"] for x in sources),
                      "slowed_legs": sum(1 for x in sources for leg in x["legs"] if leg["slowed"]),
                      "status": "in_progress", "reason": None, "note": None}
                new.append(op)
            self.operations.extend(new)
            self.wave_i += 1
            self.plan = self._plan(commit=False) if self.wave_i < len(WAVES) else {}
            e = self._log("dispatch", "", f"{_hhmm(hour)} wave: {len(new)} convoys, one per district",
                          ops=[o["op_id"] for o in new])
            return {"event": e, "operations": new}

    def outcome(self, op_id, status, reason=None, note=None):
        with self.lock:
            op = next((o for o in self.operations if o["op_id"] == op_id), None)
            if op is None or op["day"] != self.day:
                raise KeyError("unknown operation for today")
            if op["status"] != "in_progress":
                raise ValueError(f"{op_id} already reported: {op['status']}")
            if status not in ("success", "fail"):
                raise ValueError("status must be success or fail")
            self._settle(op, status, reason, note)
            replan = self._replan() if status == "fail" and self.wave_i < len(WAVES) else None
            e = self._log(f"op_{status}", op["district"],
                          f"{op_id} convoy to {op['district']} from {len(op['centres'])} centres: " +
                          ("delivered" if status == "success" else f"failed ({op['reason']})") +
                          (f". {note}" if note else ""), op_id=op_id, replan=replan)
            return {"event": e, "operation": op, "replan": replan}

    def _settle(self, op, status, reason, note):
        op["status"], op["note"] = status, (note or None)
        op["reported_at"] = datetime.utcnow().isoformat(timespec="seconds")
        d = op["district"]
        if status == "success":
            for r, a in op["items"].items():
                self.delivered[d, r] += a
        else:
            op["reason"] = reason if reason in FAIL_REASONS else "Other"
            for x in op["sources"]:               # goods go back to each centre, the need stays open
                c = x["centre"]
                for r, a in x["items"].items():
                    self.sent[d, r] -= a
                    if r == "rescue_teams":
                        self.teams_used[c] -= a
                    else:
                        self.stock[c][r] += a
                        self.budget[c][r] += a

    def simulate_outcomes(self, all_success=False):
        """Fill in the reports still missing: failures are likelier on slowed roads and long trips."""
        out = []
        for op in [o for o in self.operations if o["day"] == self.day and o["status"] == "in_progress"]:
            if all_success:
                out.append(self.outcome(op["op_id"], "success", None, "marked successful in bulk"))
                continue
            p = 0.05 + 0.10 * min(op["slowed_legs"], 2) + 0.02 * max(0.0, op["hours"] - 4)
            if self.orng.random() < p:
                reason = "Road impassable" if op["slowed_legs"] else self.orng.choice(FAIL_REASONS[1:6])
                out.append(self.outcome(op["op_id"], "fail", reason, "simulated team report"))
            else:
                out.append(self.outcome(op["op_id"], "success", None, "simulated team report"))
        return out

    # -------------------------------------------------------------- close
    def close_day(self, force=False):
        with self.lock:
            self._need_operating()
            pending = [o for o in self.operations if o["day"] == self.day and o["status"] == "in_progress"]
            if pending and not force:
                raise ValueError(f"{len(pending)} operations have no team report yet")
            for op in pending:
                self._settle(op, "fail", "No report from team", "closed without a report")
            report = self._day_report()
            self.day_reports.append(report)
            self._log("day_end", "", f"Day {self.day} closed: {report['need_met']:.0%} of need met, "
                      f"{report['ops']['success']}/{report['ops']['total']} operations succeeded", day_report=report)
            i = self.env.days.index(self.day)
            if i == len(self.env.days) - 1:
                self.done, self.phase = True, "done"
            else:
                self.env.day = self.env.days[i + 1]
                self.env._apply_events()
                self._start_day()
            return report

    def _day_report(self):
        ops = [o for o in self.operations if o["day"] == self.day]
        rows, loads, tw = [], 0.0, 0.0
        for d in self.env.districts:
            for r in RESOURCES:
                dem, got = self.truth[d][r], self.delivered[d, r]
                rows.append({"district": d, "resource": r, "demand": dem, "delivered": got, "covered": min(dem, got)})
        for o in ops:
            if o["status"] == "success":
                for x in o["sources"]:
                    for r, a in x["items"].items():
                        if r in TRUCKLOAD:
                            loads += a / TRUCKLOAD[r]; tw += x["hours"] * a / TRUCKLOAD[r]
        rec = {"day": self.day, "rows": rows, "avg_delay_hr": tw / loads if loads else 0.0, "loads": loads, "rejected": 0.0}
        self.env.log.append(rec)                     # so week metrics use the same formulas as Steps 3-6
        tot = defaultdict(lambda: [0.0, 0.0])
        for x in rows:
            tot[x["resource"]][0] += x["covered"]; tot[x["resource"]][1] += x["demand"]
        per_res = {r: (c / dm if dm > 0 else 1.0) for r, (c, dm) in tot.items()}
        ratios = [c / dm for c, dm in tot.values() if dm > 0]
        cov = {}
        for d in self.env.districts:
            rs = [x for x in rows if x["district"] == d and x["demand"] > 0]
            cov[d] = sum(x["covered"] / x["demand"] for x in rs) / len(rs) if rs else 1.0
        w = {d: 1 + self.env.vulnerability[d] for d in cov}
        worst = min(cov, key=cov.get)
        sev = self.env.severity.get(self.day, {})
        by_d = defaultdict(lambda: {"success": 0, "fail": 0})
        for o in ops:
            by_d[o["district"]][o["status"] if o["status"] in ("success", "fail") else "fail"] += 1
        districts = [{"district": d, "severity": round(sev.get(d, 0.0), 3),
                      "priority": "high" if sev.get(d, 0) >= 0.5 else "medium" if sev.get(d, 0) >= 0.3 else "low",
                      "need_met": round(cov[d], 4),
                      "need": {r: round(self.truth[d][r], 1) for r in RESOURCES},
                      "delivered": {r: round(self.delivered[d, r], 1) for r in RESOURCES},
                      "ops_success": by_d[d]["success"], "ops_fail": by_d[d]["fail"]} for d in self.env.districts]
        districts.sort(key=lambda x: x["need_met"])
        n_ok = sum(1 for o in ops if o["status"] == "success")
        lost = defaultdict(float)
        for o in ops:
            if o["status"] == "fail":
                for r, a in o["items"].items():
                    lost[r] += a
        return {"day": self.day, "policy": POLICIES[self.policy], "supply": self.supply,
                "need_met": round(sum(ratios) / len(ratios) if ratios else 1.0, 4),
                "need_met_by_resource": {r: round(v, 4) for r, v in per_res.items()},
                "worst_district": worst, "worst_need_met": round(cov[worst], 4),
                "gini": round(gini(list(cov.values())), 4),
                "vulnerability_weighted": round(sum(w[d] * cov[d] for d in cov) / sum(w.values()), 4),
                "avg_delivery_hr": round(rec["avg_delay_hr"], 2), "truckloads_delivered": round(loads, 1),
                "ops": {"total": len(ops), "success": n_ok, "fail": len(ops) - n_ok,
                        "success_rate": round(n_ok / len(ops), 4) if ops else None,
                        "fail_reasons": dict(Counter(o["reason"] for o in ops if o["status"] == "fail")),
                        "waves": self.wave_i},
                "not_delivered_after_failures": {r: round(v, 1) for r, v in lost.items()},
                "reports": {"dataset": sum(1 for x in self.reports_in if x["source"] == "dataset"),
                            "typed": sum(1 for x in self.reports_in if x["source"] == "typed")},
                "stock_left": {r: round(sum(s[r] for s in self.stock.values()), 1) for r in RESOURCES},
                "neglected": [d for d in self.env.districts if sev.get(d, 0) >= 0.3 and cov[d] < 0.25],
                "districts": districts}

    # ------------------------------------------------------------- helpers
    def _need_operating(self):
        if self.done:
            raise ValueError("the week is over; start a new session")
        if self.phase != "operate":
            raise ValueError("choose today's supply first")

    def _log(self, kind, district, detail, **extra):
        self.seq += 1
        hour = WAVES[self.wave_i - 1] if self.wave_i else 0
        e = {"seq": self.seq, "day": self.day, "time": _hhmm(hour), "type": kind, "district": district,
             "detail": detail, **extra}
        self.events.append(e)
        return e

    def since(self, seq):
        return [e for e in self.events if e["seq"] > seq]

    def state(self):
        with self.lock:
            today = [o for o in self.operations if o["day"] == self.day]
            districts = {}
            for d in self.env.districts:
                rs = [r for r in RESOURCES if self.truth[d][r] > 0]
                cov = (sum(min(1.0, self.delivered[d, r] / self.truth[d][r]) for r in rs) / len(rs)) if rs else 1.0
                nxt = defaultdict(float)
                for (c, dd, r), a in self.plan.items():
                    if dd == d:
                        nxt[r] += a
                districts[d] = {"need": {r: round(self.truth[d][r], 1) for r in RESOURCES},
                                "estimate": {r: round(self.est[d][r], 1) for r in RESOURCES},
                                "forecast": {r: round(self.forecast[d][r], 1) for r in RESOURCES},
                                "sent": {r: round(self.sent[d, r], 1) for r in RESOURCES},
                                "delivered": {r: round(self.delivered[d, r], 1) for r in RESOURCES},
                                "next_wave": {r: round(nxt[r], 1) for r in RESOURCES},
                                "need_met_so_far": round(cov, 4),
                                "severity": round(self.env.severity.get(self.day, {}).get(d, 0.0), 3)}
            trips = defaultdict(dict)
            for (c, d, r), a in self.plan.items():
                trips[(c, d)][r] = round(a, 1)
            week = summarise(episode_metrics(self.env)) if self.env.log else None
            return {"session_id": self.id, "policy": self.policy, "policy_label": POLICIES[self.policy],
                    "day": self.day, "phase": self.phase, "done": self.done,
                    "next_wave": _hhmm(WAVES[self.wave_i]) if self.wave_i < len(WAVES) and not self.done else None,
                    "waves_left": 0 if self.done else len(WAVES) - self.wave_i,
                    "supply": self.supply, "used_reports": sorted(self.used_reports), "reports": self.reports_in,
                    "plan": [{"centre": c, "centre_name": self.names[c], "district": d, "items": items,
                              "hours": round(self.travel[(c, d)], 2)} for (c, d), items in
                             sorted(trips.items(), key=lambda kv: self.travel[kv[0]])],
                    "operations": today,
                    "pending": sum(1 for o in today if o["status"] == "in_progress"),
                    "districts": districts,
                    "roads": {str(k): "blocked" if s == "blocked" else ("slowed" if t > self.base_tt[k] + 1e-6 else "open")
                              for k, (s, t) in self.roads.items()},
                    "stock": {c: {r: round(v, 1) for r, v in s.items()} for c, s in self.stock.items()},
                    "stock_left": {r: round(sum(s[r] for s in self.stock.values()), 1) for r in RESOURCES},
                    "vehicles": dict(self.vehicles),
                    "day_reports": self.day_reports, "week": week, "fail_reasons": FAIL_REASONS,
                    "last_seq": self.seq}


OPS: dict[str, OpsSession] = {}
