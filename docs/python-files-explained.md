# Every Python file explained, with its main formula

These are the 15 `.py` files written for Steps 0-3 (your team's `scripts/phase1/` files are not included). Each entry says **what the file does**, **its main formula in plain words**, and **what it reads and writes**. The `__init__.py` files are empty; they just let Python treat each folder as a package.

---

## Data preparation

### 1. `scripts/simulate_relief_data.py`: makes the simulated flood week

**What it does:** we have no real relief-centre data, so this builds a realistic 7-day scenario from your real district data.

**Main formulas:**

- **Road length between two districts**
  `road km = straight-line km between the two HQs × 1.35`
  (Roads wind, so they're about 35% longer than a straight line. The straight-line distance uses the haversine formula for distance on a globe.)
  `travel time (hours) = road km ÷ 35 km/h`

- **People displaced in a district on a given day**
  `displaced = population × flood exposure (100-yr) × 15% × (1 + vulnerability) × day severity × random noise (±10%)`
  - *Flood exposure* is the share of the district that floods.
  - *(1 + vulnerability)* means poorer, more vulnerable districts have more people needing help.
  - *Day severity* follows the flood's shape: 0.3, 0.7, **1.0**, 0.9, 0.6, 0.4, 0.25 (peak on day 3).

- **What displaced people need each day**
  `food kits = displaced × 0.25` (one kit per family of 4)
  `water litres = displaced × 15` (minimum drinking + cooking water)
  `medicine kits = displaced × 0.02` (one kit per 50 people)
  `rescue teams = displaced ÷ 20,000` (rounded up, only on bad days)

- **Urgency of a district on a day (0 to 1)**
  `urgency = day severity × (flood exposure ÷ 0.45) × (0.5 + vulnerability)`

- **Stock at each relief centre**
  `stock = 70% of the whole week's total need × (this centre's share of population) × random (0.8 to 1.2)`
  So there's never enough, and supplies sit where people live, not where the flood is.

- **Chance a road closes today**
  `chance = 45% × (how flooded its worst end is, compared with the most flooded district) × day severity`
  A closed road reopens with a 35% chance each day once the peak has passed.

**Reads:** `data/processed/graph_nodes.csv`, `graph_edges.csv`
**Writes:** `data/simulated/` → `district_locations.csv`, `road_edges.csv`, `relief_centres.csv`, `demand_timeline.csv`, `road_events.csv`, `scenario_config.json`

---

### 2. `scripts/fetch_osm_roads.py`: real road distances (on hold)

**What it does:** downloads Kerala's major roads from OpenStreetMap and finds the real shortest drive between neighbouring district HQs.

**Main formula:**
`road distance = shortest path along real roads (Dijkstra's algorithm)`
`travel time = sum over each road piece of (length ÷ speed limit)`, using 80/60/50/40 km/h for motorway/trunk/primary/secondary if no limit is tagged.

**Writes:** `data/processed/road_edges_osm.csv` (would replace the estimated distances). It's on hold because the download was too slow.

---

## Step 1: reading the tweets (`ml/nlp/`)

### 3. `ml/nlp/train_classifier.py`: sorts tweets into 9 categories

**What it does:** learns to label a tweet as *urgent request, damage report, injured/dead, displaced, rescue/donation, caution, sympathy, other, not humanitarian*.

**Main formulas:**

- **Cleaning:** links become "URL", @names become "USER", # signs are removed, and everything is lower-cased.
- **TF-IDF (turns text into numbers):**
  `score of a word in a tweet = (how often it appears in this tweet) × log(total tweets ÷ tweets containing it)`
  Common words like "the" get almost zero; telling words like "stranded" get high scores. It does this for single words, word pairs, and 2-5 letter chunks (which catch spelling variations).
- **Logistic regression (the classifier):**
  `chance of category k = e^(score_k) ÷ sum of e^(score) over all categories`, where `score_k = sum of (word weight for category k × TF-IDF value)`
  Training adjusts the weights so the right category gets the highest chance. `class_weight="balanced"` makes rare categories (like displaced people) count more, so the model doesn't ignore them.
- **Choosing the setting C** (how strictly to fit): it tries 8 values and keeps the one with the best **macro-F1** on the dev set.
  `F1 = 2 × precision × recall ÷ (precision + recall)`; *macro-F1* is the plain average of F1 across all 9 categories.

**Reads:** `data/raw/humaid_kerala_2018/{train,dev,test}.csv`
**Writes:** `ml/nlp/models/tweet_classifier.joblib`, `ml/nlp/results/classifier_report.md`
**Result:** macro-F1 0.595, accuracy 70.5%

---

### 4. `ml/nlp/gazetteer.py`: finds which district a tweet is about

**What it does:** a dictionary of about 200 place names, each pointing to its district (e.g. Chengannur → Alappuzha, Aluva → Ernakulam, Ranni → Pathanamthitta).

**Main rule:**
`districts mentioned = every district whose names appear in the tweet as whole words`, sorted by how many times each is mentioned.
Short ambiguous words ("pala", "mala") only count if the tweet also says "Kerala" or the district name.

---

### 5. `ml/nlp/needs.py`: what is needed and how urgent

**What it does:** spots resource needs and scores urgency using keyword rules.

**Main formulas:**

- **Resources:** a need is flagged if any of its keywords appear.
  food ← "food, rice, meals, hungry, baby food…"; water ← "drinking water, food and water…"; medicine ← "medicine, insulin, doctor…"; rescue ← "stranded, trapped, boat, rooftop…"; shelter ← "relief camp, blankets, displaced…"
  If no keyword matches, the category decides: displaced → shelter, injured → medicine, damage → rescue.
- **Urgency score (0 to 1):**
  `urgency = category base × model confidence + 0.1 per urgency word (max 0.3) + 0.1 if a phone number is present`
  - *Category base:* urgent request 0.6, displaced 0.5, injured 0.5, damage 0.35, caution 0.2, rescue/donation 0.15, other 0.1, sympathy and not humanitarian 0.
  - *Urgency words:* "urgent, trapped, elderly, no food, water rising, since yesterday…"
  - Sympathy and not-humanitarian tweets are capped at 0.2.

---

### 6. `ml/nlp/extract_reports.py`: turns all tweets into district data

**What it does:** runs files 3-5 on all 7,984 tweets and adds up the results per district per day.

**Main formulas:**

- **When the tweet was posted** (HumAID has no date column, but Twitter IDs hide the time):
  `time in milliseconds = (tweet ID ÷ 2²²) + 1,288,834,974,657`
- **Actionable:** the tweet is a useful category *and* names at least one need.
- **Daily district need for each resource:**
  `need_food (district, day) = sum of urgency over that day's actionable tweets in that district that mention food` (same for the other resources)
  So one very urgent request counts more than several mild ones.

**Writes:** `data/processed/crisis_reports.csv` (one row per tweet) and `district_daily_signals.csv` (per day and district: report count, urgency total, need per resource)

---

## Step 2: graph model and severity (`ml/gnn/`)

### 7. `ml/gnn/dataset.py`: builds one district map per day

**What it does:** makes 26 daily graphs (17 Aug to 12 Sep 2018). Each district is a node, and each shared border is an edge carrying travel time.

**Main formulas:**

- **Static features (9 per district):** log(population), rural share = rural ÷ total, vulnerability, and the 6 flood exposures. Each is standardised:
  `standardised value = (value − average) ÷ spread`, so all features are on a similar scale.
- **Daily features (10 per district):** log(1 + x) of the day's reports, actionable reports, urgency total and the 5 needs, plus
  `trailing urgency = average urgency of the last 2 days`
  `statewide urgency = total urgency across all districts ÷ 14`
  The log(1 + x) squashes big numbers, so Ernakulam's 50 reports don't swamp everything.
- **Edge feature:** `travel time ÷ the longest travel time` (scaled 0-1).
- **What to predict:** `log(1 + tomorrow's urgency total)` for each district.

---

### 8. `ml/gnn/models.py`: the three neural networks

**Main formulas:**

- **MLP (no graph):** each district is predicted only from its own 19 numbers, through two layers.
  `layer output = ELU(weights × input + bias)`. ELU is a smooth "keep positives, squash negatives" function.
- **GCN:** each district first averages its own and its neighbours' numbers, then applies weights.
  `new district value = weights × average over (itself + neighbours), scaled by how many neighbours each has`
- **GAT (the main model):** like GCN, but **it learns how much to listen to each neighbour.**
  `attention score (i ← j) = LeakyReLU(a · [W·x_i , W·x_j , travel-time feature])`
  `attention weight = e^(score) ÷ sum of e^(score) over all of i's neighbours` (so the weights add up to 1)
  `new value of i = sum over neighbours of (attention weight × W·x_j)`
  It uses 4 "heads" (4 independent attention patterns) in layer 1 and 1 head in layer 2, plus a **skip connection** (`output = graph part + direct copy of own features`) so a district never loses its own information.

---

### 9. `ml/gnn/train.py`: trains the models and writes severity

**What it does:** trains MLP, GCN and GAT 5 times each, compares them, and produces the daily severity score.

**Main formulas:**

- **Training loss:** `mean squared error = average of (prediction − actual)²`, minimised with the Adam optimiser (learning rate 0.01). It stops early if the validation error hasn't improved for 60 rounds.
- **Evaluation:**
  `MAE = average of |prediction − actual|`
  `RMSE = √(average of (prediction − actual)²)`
  - *Temporal test:* train on 18-31 Aug, check on 1-5 Sep, test on 6-12 Sep.
  - *Spatial test:* hide 4 districts (Kottayam, Malappuram, Wayanad, Kollam) during training, then test on them.
  - *Baseline:* "tomorrow = today".
- **Severity score (the output used in Step 3):**
  `severity = 0.5 × predicted need (scaled 0-1) + 0.3 × 100-yr flood exposure (scaled 0-1) + 0.2 × vulnerability`
  `class: high if ≥ 0.5, medium if ≥ 0.3, else low`
- **Attention table:** the GAT's layer-1 attention weight for each road, averaged over the training days.

**Writes:** `ml/gnn/models/gat.pt`, `ml/gnn/results/gnn_report.md`, `attention_edges.csv`, `data/processed/district_severity_daily.csv`

---

## Step 3: simulator and baselines (`ml/env/`, `ml/baselines/`)

### 10. `ml/env/relief_env.py`: the 7-day simulator

**What it does:** a "board game" for sharing out supplies. Each day a strategy says *send X of resource R from centre C to district D*. The simulator applies the rules and moves to the next day.

**Main rules and formulas:**

- **Trucks per centre per day** `= vehicles × 2 trips`
  `1 truckload = 1,000 food kits, or 25,000 L of water, or 500 medicine kits`
  `trucks used = amount sent ÷ truckload size`
- **Can't send more than you have:**
  `sent = smallest of (amount asked, stock left, trucks left × truckload size)`
- **Travel time centre → district**
  `= 1 hour (local delivery) + shortest drive over roads that are open today` (Dijkstra's algorithm via `networkx`)
  If every road to a district is blocked, it can't be reached that day.
- **Road events:** blocked roads are removed, slowed roads take `travel time ÷ 0.5` (twice as long), and reopened roads go back to normal.
- **Covered need:** `covered = smaller of (delivered, demand)`. Extra deliveries are wasted, and unmet need is not carried to the next day.
- Food, water and medicine leave stock when sent. Rescue teams return and can be sent somewhere new each day.
- **Daily score:** `average over resources of (total covered ÷ total demand)`

---

### 11. `ml/env/metrics.py`: the scorecard

**Main formulas** (over all 7 days):

- **Fulfilment** `= average over the 4 resources of (total covered ÷ total demand)`
- **Vulnerability-weighted coverage** `= sum of (1 + vulnerability) × coverage ratio ÷ sum of (1 + vulnerability)`, so vulnerable districts count more
- **Worst district** `= lowest average coverage of any district`
- **Gini coefficient (fairness)** `= (2 × Σ rank × value) ÷ (n × Σ value) − (n + 1) ÷ n`, over district coverages sorted from low to high
  0 = every district equally covered, closer to 1 = very unequal
- **Average delivery time** `= Σ (travel hours × truckloads) ÷ Σ truckloads`
- **Neglected district-days** `= number of (district, day) pairs where severity ≥ 0.3 but coverage < 25%`

---

### 12. `ml/baselines/policies.py`: four ways to share supplies

- **Local-first:** each centre fills its own district first, then the next nearest, until it runs out. No formula, just nearest-first.
- **Greedy by severity:** sort districts by severity (highest first); fill each from the nearest centres that still have stock.
- **LP: max coverage (OR-Tools linear programming):** each day it solves
  - **maximise** `Σ over districts and resources of (covered ÷ total demand of that resource)  −  0.01 × travel penalty`
  - **subject to:**
    - `covered ≤ demand` and `covered ≤ total sent to that district`
    - `total sent from a centre ≤ its stock` (per resource)
    - `total truckloads from a centre ≤ its trucks`
    - only reachable (centre, district) pairs can be used
  - Everything is measured in truckloads, so the numbers stay a similar size and the solver stays stable.
- **LP: fairness-aware:** same rules, but the goal becomes
  `0.5 × (the coverage goal above, weighted) + 4 × average of [weight × covered ÷ demand] per district + 4 × z`
  - `weight = (1 + vulnerability) × (0.5 + severity)`, so vulnerable, badly hit districts count more
  - `z` = the **worst** district's coverage ratio (every district must have `covered ÷ demand ≥ z`), so raising z lifts the worst-off district

---

### 13. `ml/baselines/evaluate.py`: runs the comparison

**What it does:** plays each strategy through all 7 days of the simulator (`reset`, then `step` × 7), scores it with `metrics.py`, and writes the tables.

**Writes:** `ml/baselines/results/baseline_report.md`, `baseline_metrics.csv`, `per_district.csv`

---

## The whole pipeline in one line

`tweets → (3, 4, 5, 6) need + urgency per district per day → (7, 8, 9) GAT → severity per district → (10, 11) simulator + scorecard ← (1) simulated centres, demand and roads → (12, 13) compare strategies`
