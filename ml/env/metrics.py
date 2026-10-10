"""Episode metrics shared by baselines and RL agents."""
from collections import defaultdict


def gini(values):
    v = sorted(values)
    n = len(v)
    if n == 0 or sum(v) == 0:
        return 0.0
    cum = sum((i + 1) * x for i, x in enumerate(v))
    return (2 * cum) / (n * sum(v)) - (n + 1) / n


def episode_metrics(env, neglect_threshold=0.25, severity_threshold=0.3):
    res_cov, res_dem = defaultdict(float), defaultdict(float)
    dist_cov, dist_dem = defaultdict(float), defaultdict(float)
    vw_cov = vw_dem = 0.0
    neglect = 0
    delays, loads = 0.0, 0.0
    for rec in env.log:
        day_ratio = defaultdict(list)
        for row in rec["rows"]:
            if row["demand"] <= 0:
                continue
            r, d = row["resource"], row["district"]
            ratio = row["covered"] / row["demand"]
            res_cov[r] += row["covered"]; res_dem[r] += row["demand"]
            dist_cov[d] += ratio; dist_dem[d] += 1
            v = 1 + env.vulnerability[d]
            vw_cov += v * ratio; vw_dem += v
            day_ratio[d].append(ratio)
        for d, rs in day_ratio.items():
            if env.severity.get(rec["day"], {}).get(d, 0) >= severity_threshold and \
                    sum(rs) / len(rs) < neglect_threshold:
                neglect += 1
        delays += rec["avg_delay_hr"] * rec["loads"]; loads += rec["loads"]
    per_resource = {r: res_cov[r] / res_dem[r] for r in res_dem}
    per_district = {d: dist_cov[d] / dist_dem[d] for d in dist_dem}
    return {
        "fulfilment": sum(per_resource.values()) / len(per_resource),
        **{f"fulfil_{r}": v for r, v in per_resource.items()},
        "vuln_weighted_fulfilment": vw_cov / vw_dem,
        "worst_district_fulfilment": min(per_district.values()),
        "gini": gini(list(per_district.values())),
        "avg_delay_hr": delays / loads if loads else 0.0,
        "neglect_district_days": neglect,
        "per_district": per_district,
    }
