# Dashboard guide: what everything does

The dashboard shows the August 2018 Kerala flood week (Day 1 = 18 Aug to Day 7 = 24 Aug) as a relief coordinator would see it. It opens in a dark "control room" look with four areas:

- **Far left, the navigation rail:** the five sections (Overview, Alerts, Results, Simulate, What-if), plus **Help** (the quick-start guide that pops up on first visit) and a **Light / Dark** switch.
- **Left panel:** the section you picked, with a one-line explanation at the top.
- **Centre, the map:** with floating controls on top of it.
- **Right column, "Today at a glance":** the day's headline numbers, the 5 worst-hit districts and the latest alerts. On smaller laptop screens this column is hidden and the numbers move into the Overview panel. On a phone the sections move to a bar at the bottom.

Everything comes from the backend (FastAPI + PostGIS), which serves the results of Steps 1-6.

---

## 1. Controls on the map

| Control | Where | What it does |
|---|---|---|
| **Day timeline (Day 1 … Day 7)** | bottom centre | Picks the day. The map, the right-hand column, Overview and Alerts all switch to that day. While a simulation runs, it shows the simulated day instead. |
| **▶ Play** | left of the timeline | Plays the week automatically, one day every 1.6 seconds, so you can watch the flood rise and fall. Press again to pause. |
| **Severity / Need met** | top right | Colours each district by its **GAT severity score** (Step 2, light to dark orange) or by **how much of its need that day's plan covers** (light to dark blue). "Need met" shows *fairness* at a glance: a pale district is being left behind. |
| **Streets** | top right | Shows or hides the street map underneath (needs internet). |
| **Roads** | top right | Shows or hides the 21 district-to-district road links. |
| **Centres** | top right | Shows or hides the 19 relief centres. |
| **Shipments** | top right | Shows or hides the glowing blue lines for the day's planned deliveries. |
| **+ / −** | bottom right | Zoom. You can also scroll and drag. |

## 1b. Right column: today at a glance

- **People displaced**, **districts at high severity** (score ≥ 0.5), **alerts raised today** and **share of today's need planned** (the average over food, water, medicine and rescue teams).
- **Most affected:** the 5 districts with the highest severity, each with a bar.
- **Latest alerts:** the newest 4 alerts, with a link to the full list in the Alerts section.

## 2. The map

- **Districts (14 shapes):** hover over one to see its severity score and class, displaced people, food and water needed, and vulnerability index.
- **Roads:** green solid = open, yellow dashed = slowed, red dotted and blinking = blocked. Hover to see the current travel time. The road status changes day by day with the flood.
- **Relief centres (white circles in dark mode, black in light mode):** a bigger circle means more vehicles. Hover to see the stock (food, water, medicine, rescue teams, vehicles).
- **Shipments (glowing blue lines):** from a centre to a district. The dashes move in the direction of travel, and a thicker line means more truckloads. Only the 25 biggest are drawn, so the map stays readable. Hover to see the exact truckloads.
- **Legend (top left, under the date):** explains the colours. Click its title to fold it away.
- You can zoom and pan as normal.

---

## 3. Tab: Overview

A one-glance summary of the chosen day.

- On smaller screens, the four headline numbers from the right-hand column appear here first.
- **Severity by district:** a bar chart of all 14 districts, ranked by GAT severity, using the same colours as the map. This is where Step 2 shows up.
- **Share of today's need covered by the plan:** for food, water, medicine and rescue teams, how much of the total need the AI agents' plan (Step 6) ships that day. It's what was *planned*, not what was delivered: a truck on a road that turns out blocked doesn't arrive.

## 4. Tab: Alerts & events

The **reallocation loop (Step 6)** for the chosen day, in time order. This is where the NLP (Step 1) and replanning connect.

- **Filter buttons**, each with a count:
  - **Alerts ⚠:** raised in three cases: tweets change a district's estimated need by 30% or more, a district is **cut off** (no open road from any centre), or a fairly severe district is **neglected** (under 25% of its need met that day).
  - **Reports:** real **HumAID tweets** that the Step 1 NLP classified (need type, urgency) and placed in a district. Off by default because there are many.
  - **Dispatches:** the 4 dispatch waves per day, each saying what was sent.
  - **Roads:** a road becoming slowed, blocked or reopened.
- Each line shows the **time**, the **type**, the **district** and the detail (for example the tweet text, or what was dispatched).

Point to make in a demo: new tweets and road changes come in during the day → the system replans at the next dispatch wave. In our tests, this replanning raised demand met from 60.5% to 62.7%.

## 5. Tab: Results

The comparison of all the methods (the evaluation slide). Average over **50 unseen flood weeks**.

- **Three measure buttons:**
  - **Demand met:** share of all need that was delivered (higher is better).
  - **Worst-off district:** coverage of the single worst-served district (higher is fairer).
  - **Gini:** inequality between districts (lower is fairer; 0 = perfectly equal).
- **Allocation strategies chart (Steps 3-4):** Local-first, Greedy, the three OR-Tools optimisers, the three MAPPO versions (no fairness, fairness, strong fairness) and the **hindsight optimum** (an upper bound that knows the whole week in advance, which no real system can).
- **Value of replanning chart (Step 6):** static morning plan vs reacting to roads, to tweets, to both (dynamic), and "perfect" (knows everything).
- **Federated learning table (Step 5):** centralised training vs Flower federated (FedAvg) vs each centre training alone.

The headline: the optimiser meets slightly more demand, but **the AI agents with the fairness reward are much fairer** (Gini 0.019 vs 0.060, worst district about 75% vs 56%).

## 6. Tab: Simulate

Plays the official flood week **live** through the backend, one day at a time.

1. **Strategy:** choose who makes the decisions: *AI agents (MAPPO + fairness)*, the three optimiser versions, *Greedy by severity* or *Local-first*.
2. **Start week** (or **Restart**).
3. **Play day N** steps one day at a time; **Play to end** runs the rest of the week.
4. **Close a road from today on:** pick a road and click **Close**. The strategy has to work around it from that day on. Roads you've closed are listed underneath.

While it runs:
- The **map** follows the simulation: the latest day's shipments, and (with "Share of need met") which districts are covered.
- **Day by day chart:** demand met and worst-off district for each day.
- **Week so far tiles:** demand met, worst-off district and Gini.

Good demo: start with the AI agents, play Day 1, close **Alappuzha – Kottayam**, then Play to end. Then restart with "Optimiser, max coverage" and compare the worst-off district.

## 7. Tab: What-if

Changes the scenario and replays the **whole week**, then compares it with the normal week.

- **Strategy:** same choices as Simulate.
- **Stock slider (30%-200%):** less or more relief supplies than normal.
- **Demand slider (50%-200%):** a smaller or bigger disaster.
- **Close roads for the whole week:** tick any roads.
- **Run what-if** → a table with **Normal week**, **What-if** and **Change** (green ▲ better, red ▼ worse, percentages in points) for:
  - Demand met
  - Vulnerability-weighted coverage (counts poorer, more vulnerable districts more)
  - Worst-off district
  - Gini
  - Delivery time (hours)
  - Neglected district-days (days a district got almost nothing)

Good demo: set stock to 50% and run it for the AI agents, then for "Optimiser, max coverage". With less stock, you can see which strategy shares the shortage more fairly.

---

## Where each project step shows up

| Step | Where on the dashboard |
|---|---|
| 1. NLP on HumAID tweets | Alerts & events → Reports |
| 2. GAT severity | Map colour "Severity", Overview severity chart |
| 3. Baselines (optimiser, greedy, local-first) | Results chart, Strategy choice in Simulate / What-if |
| 4. MAPPO with fairness reward | Results chart, "AI agents" strategy, shipments on the map |
| 5. Federated learning (Flower) | Results → Federated learning table |
| 6. Dynamic reallocation loop | Alerts & events, Overview "share covered", Results "Value of replanning" |
| 7. FastAPI + PostGIS | Feeds everything (http://localhost:8000/docs lists the API) |
