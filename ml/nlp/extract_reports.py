"""Turn HumAID tweets into structured crisis reports and daily district demand
signals for the graph model and the reallocation loop.

Each tweet gets: post time (from the tweet-ID snowflake), predicted category
and confidence, districts mentioned, resource needs and an urgency score.
Labels are predicted by the trained classifier (as they would be on a live
feed); the gold HumAID label is kept for evaluation.

Usage: python -m ml.nlp.extract_reports
Outputs:
  data/processed/crisis_reports.csv          one row per tweet
  data/processed/district_daily_signals.csv  date x district: report counts,
                                             urgency-weighted need per resource
"""
import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import joblib

from ml.nlp.gazetteer import find_districts
from ml.nlp.needs import RESOURCE_KEYWORDS, find_resources, urgency_score
from ml.nlp.train_classifier import clean

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "raw" / "humaid_kerala_2018"
OUT = ROOT / "data" / "processed"
MODEL = ROOT / "ml" / "nlp" / "models" / "tweet_classifier.joblib"
TWITTER_EPOCH_MS = 1288834974657
RESOURCES = list(RESOURCE_KEYWORDS)
ACTIONABLE = {"requests_or_urgent_needs", "displaced_people_and_evacuations",
              "injured_or_dead_people", "infrastructure_and_utility_damage",
              "caution_and_advice", "rescue_volunteering_or_donation_effort",
              "other_relevant_information"}


def tweet_time(tweet_id):
    ms = (int(tweet_id) >> 22) + TWITTER_EPOCH_MS
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def main():
    model = joblib.load(MODEL)
    rows = []
    for split in ["train", "dev", "test"]:
        with open(DATA / f"{split}.csv", newline="", encoding="utf8") as f:
            for r in csv.DictReader(f):
                r["split"] = split
                rows.append(r)

    probs = model.predict_proba([clean(r["tweet_text"]) for r in rows])
    classes = model.classes_

    reports = []
    for r, p in zip(rows, probs):
        i = p.argmax()
        label, conf = classes[i], float(p[i])
        text = r["tweet_text"]
        districts = find_districts(text)
        resources = find_resources(text, label)
        ts = tweet_time(r["tweet_id"])
        reports.append({
            "tweet_id": r["tweet_id"],
            "posted_utc": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "date": ts.strftime("%Y-%m-%d"),
            "split": r["split"],
            "gold_label": r["class_label"],
            "pred_label": label,
            "pred_confidence": round(conf, 3),
            "districts": "|".join(districts),
            "primary_district": districts[0] if districts else "",
            "resources": "|".join(resources),
            "urgency": urgency_score(text, label, conf),
            "actionable": int(label in ACTIONABLE and bool(resources)),
            "text": text.replace("\n", " "),
        })
    reports.sort(key=lambda x: x["posted_utc"])

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "crisis_reports.csv", "w", newline="", encoding="utf8") as f:
        w = csv.DictWriter(f, fieldnames=list(reports[0]))
        w.writeheader()
        w.writerows(reports)

    # Daily district signals: only located, actionable reports count toward need.
    agg = defaultdict(lambda: {"reports": 0, "actionable_reports": 0, "urgency_sum": 0.0,
                               **{f"need_{r}": 0.0 for r in RESOURCES}})
    for rep in reports:
        if not rep["primary_district"]:
            continue
        a = agg[(rep["date"], rep["primary_district"])]
        a["reports"] += 1
        if rep["actionable"]:
            a["actionable_reports"] += 1
            a["urgency_sum"] += rep["urgency"]
            for res in rep["resources"].split("|"):
                a[f"need_{res}"] += rep["urgency"]
    signals = [{"date": d, "district": k, **{key: round(v, 3) if isinstance(v, float) else v
                                           for key, v in a.items()}}
               for (d, k), a in sorted(agg.items())]
    with open(OUT / "district_daily_signals.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(signals[0]))
        w.writeheader()
        w.writerows(signals)

    located = sum(1 for r in reports if r["primary_district"])
    actionable = sum(r["actionable"] for r in reports)
    print(f"tweets={len(reports)} located={located} ({located/len(reports):.1%}) "
          f"actionable={actionable} located_actionable="
          f"{sum(1 for r in reports if r['actionable'] and r['primary_district'])}")
    print(f"signal rows={len(signals)}")


if __name__ == "__main__":
    main()
