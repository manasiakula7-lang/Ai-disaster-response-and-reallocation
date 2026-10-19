# Dashboard guide: what everything does

RESPONDA shows the August 2018 Kerala flood week (Day 1 = 18 Aug to Day 7 = 24 Aug) as a relief coordinator would see it, using the results of Steps 1-6 served by the backend (FastAPI + PostGIS).

**Layout.** The sidebar on the left has the six pages. Each page has a big title at the top and, on the right, the **day picker**: changing the day updates every page that shows "today". On a phone the sidebar becomes a scrollable bar at the top.

**Words used everywhere**

| Word | Meaning |
|---|---|
| Flood priority | The district's severity score from the GAT (Step 2): 50% predicted demand, 30% 100-year flood exposure, 20% social vulnerability. **High** ≥ 0.5, **Moderate** ≥ 0.3, otherwise **Low**. |
| Need / demand | Food kits, water (litres), medicine kits and rescue teams a district needs that day. |
| Need met / demand met | Share of the need that was actually delivered. |
| Worst-off district | The district with the lowest need met. Our fairness measure. |
| Gini | Fairness gap between districts: 0 = every district gets the same share, higher = less fair. |
| AI agents | The 19 relief centres running the trained multi-agent PPO policy with the fairness term (Step 4). |
| Optimiser | The OR-Tools linear programme baselines (Step 3). |
| Dispatch wave | The reallocation loop (Step 6) replans four times a day: 06:00, 12:00, 18:00, 24:00. |

---

## 1. Overview: "Kerala Command Centre"

![Overview](screenshots/1-overview.png)

- **Four cards:** mapped districts (with how many are High / Moderate today), relief centres, crisis reports today (real tweets and alerts raised), road links (how many are blocked today).
- **Flood priority map:** districts coloured High (red), Moderate (amber), Low (teal). Hover for details.
- **Incident feed:** the day's real crisis tweets that the system acted on, most urgent first, with district, time, category and urgency. Click one to open it in **Decision Support**.

## 2. GIS Intelligence

![GIS](screenshots/2-gis.png)

- **Map layers:** switch the street map, roads, relief centres and shipments on or off. Roads show today's status (blocked red dashed, slowed amber). Shipments are glowing blue lines from centre to district.
- **Colour districts by:** flood priority class, severity score, or need met (how much of today's need the AI agents' plan ships; a pale district is being left behind).
- **Day timeline with ▶ play:** steps through the week so you can watch the flood rise and fall.
- **District status table:** every district's priority class, score, displaced people and how much of its need the plan covers that day.

## 3. GAT Network

![GAT network](screenshots/3-network.png)

The graph the GAT model actually works on: 14 district nodes, 21 road links and the 19 relief centres.

- **Node colour and size:** flood priority; the number inside is today's priority rank.
- **Link width:** how much attention the GAT pays to that neighbour (learned in Step 2). Red dashed = road blocked today.
- **Small house icons:** relief centres, joined to their home district.
- **Click a district** to see its details on the right: priority score and rank, flood exposure, vulnerability, population, rural share, its neighbours (with attention; red outline = road blocked), its relief centres, and its **GAT embedding**: the 16 hidden features the network computed for that district on that day before predicting tomorrow's demand.

## 4. Decision Support

![Decision support](screenshots/4-decision.png)

Follows one crisis report from tweet to trucks.

1. **Select a crisis report:** real tweets from that day the reallocation loop acted on, most urgent first. You see the text, needs found, category, model confidence and urgency.
2. **Four cards:** affected district (people displaced), flood priority and rank, resource types asked, how many centres contributed at the next wave.
3. **Today's need vs planned:** per resource, the district's need and how much the plan ships across all four waves.
4. **Shipments at the next wave:** which centres sent what to that district at the first dispatch after the report, nearest first, with road hops and travel time.
5. **How the district fares under each strategy:** share of its need met over the whole week, AI agents vs the other strategies.
6. **Why was this decision recommended?** Six plain-language steps: NLP reading, location, demand update, GAT priority, allocation, fairness check.

![Decision explanation](screenshots/4b-decision-explain.png)

## 5. Resource Allocation

![Resource allocation](screenshots/5-allocation.png)

The allocation simulator: plays the whole flood week with two strategies on the same scenario.

- **Scenario:** official week as it happened, supply shortage (half the stock), bigger flood (+50% demand), main roads cut (Alappuzha–Ernakulam and Ernakulam–Thrissur), or worst case (half stock and +50% demand).
- **Strategy** and **Compare with:** any of AI agents, the three optimisers, greedy by severity, local-first. Default: AI agents vs optimiser + rationing.
- **Cards:** demand met, worst-off district, fairness gap (Gini) and average delivery time, each with the difference from the comparison strategy.
- **Delivered and unmet resources:** per resource, both strategies side by side.
- **Daily chart:** demand met per day for both.
- **District-level allocation analysis:** every district's need met, switchable between the two strategies and between resources.
- **Allocation summary** and **disaster event timeline:** what changed each day (demand surges, roads blocked, slowed or reopened) that both strategies had to replan around.

![District-level allocation](screenshots/5b-allocation-districts.png)

## 6. Model Analytics

![Model analytics](screenshots/6-analytics.png)

- **Disaster report analytics (Step 1):** classifier macro-F1 and accuracy, urgency AUROC, how many tweets were placed in a district, needs mentioned, where reports came from; **F1 by tweet category**.
- **GAT demand forecast error (Step 2):** error of persistence, MLP, GCN and GAT on later days or unseen districts, and the strongest learned attention links.
- **Training reward (Step 4):** MAPPO learning curves for the three fairness settings.
- **Which allocation strategy works best? (Steps 3-6):** the full comparison over 50 unseen flood weeks: demand met, worst-off district, Gini.
- **Federated learning (Step 5):** 19 centres training with Flower FedAvg, federated vs centralised vs independent models, and fairness over the training rounds.

## Phone

![Mobile](screenshots/7-mobile.png)

---

*Screenshots were taken without map tiles (not reachable from the build machine); with internet the street map shows under the districts.*
