# Code walkthrough (Steps 0-3), in simple words

Everything runs from the repo root with Python. Each step reads files written by the step before it, so they run in order.

```
data/            all the data (raw → processed → simulated)
scripts/         data preparation
ml/nlp/          Step 1: reading tweets
ml/gnn/          Step 2: graph model + severity
ml/env/          Step 3: the simulator
ml/baselines/    Step 3: allocation strategies we compare against
```

---

## Step 0: Data preparation (`scripts/`)

### `scripts/phase1/` (your team's code)
These built the 14-district dataset: population, vulnerability index (from NFHS-5), flood exposure (from the KSDMA flood maps) and which districts touch each other. I only changed the file paths. `validate_phase1.py` checks everything is consistent, and it passes.

### `scripts/simulate_relief_data.py` (new)
We have no real relief-centre data, so this script **makes up a realistic flood week**:
1. **District locations**: the official HQ coordinates from your shapefile.
2. **Roads**: for each pair of neighbouring districts, the straight-line distance × 1.35 (roads aren't straight), then travel time at 35 km/h.
3. **Daily demand** for 7 days: *people displaced = population × flood exposure × 15% × (1 + vulnerability) × how bad that day is* (the flood peaks on day 3). From that it works out food (1 kit per 4 people), water (15 L per person) and medicine (1 kit per 50 people), plus rescue teams.
4. **19 relief centres**: one per district (two in big districts), stocked with only **70% of what the week needs**. Stock is placed by population, not by flood risk, so it starts in the wrong places on purpose.
5. **Road events**: each day some roads close or slow down. Roads near badly flooded districts are more likely to close.

It uses a fixed random seed, so it gives the same files every time. All the assumptions are saved in `scenario_config.json`.

### `scripts/fetch_osm_roads.py` (new, on hold)
Would replace the estimated road distances with real ones from OpenStreetMap. It's paused because the download was too slow.

---

## Step 1: Reading the tweets (`ml/nlp/`)

| File | What it does, simply |
|---|---|
| `train_classifier.py` | Teaches the computer to sort tweets into the 9 HumAID categories (urgent request, damage report, sympathy...). It turns each tweet into word and letter-pattern counts (**TF-IDF**) and learns which patterns go with which category (**logistic regression**). It tries 8 settings, keeps the best on the dev set, then tests once on the test set. Saves the model to `models/tweet_classifier.joblib`. |
| `gazetteer.py` | A hand-made dictionary of about 200 place names (Chengannur → Alappuzha, Aluva → Ernakulam, Chalakudy → Thrissur...). `find_districts(text)` returns the districts a tweet mentions. |
| `needs.py` | Keyword rules. `find_resources()` spots needs ("rice", "drinking water", "insulin", "stranded", "relief camp" map to food, water, medicine, rescue and shelter). `urgency_score()` gives 0-1 based on the category, how sure the model is, words like "urgent / trapped / elderly", and whether a phone number is included. |
| `extract_reports.py` | Runs all of the above on every tweet. It also gets each tweet's date from its ID number. It writes two files: `crisis_reports.csv` (one row per tweet) and `district_daily_signals.csv` (per day, per district: how many reports and how much of each need). |

**Result:** about 71% of tweets are categorised correctly and 81% of urgent requests are caught. Only 14% of tweets name a place.

---

## Step 2: Graph model and severity (`ml/gnn/`)

| File | What it does, simply |
|---|---|
| `dataset.py` | Builds **one graph per day** (17 Aug to 12 Sep 2018). Each district is a dot, each shared border is a line, and the line carries the travel time. Each district has 19 numbers: fixed ones (population, vulnerability, flood risk) and daily ones from Step 1 (reports, urgency, needs). The thing to predict is **tomorrow's need** in each district. |
| `models.py` | Three models. **MLP** looks at each district alone. **GCN** averages in its neighbours. **GAT** also averages in neighbours, but *learns how much attention to pay to each neighbour*. That's the model named in the deck. |
| `train.py` | Trains all three (5 times each, to be fair), compares them with the simplest guess ("tomorrow = today"), and saves the GAT. Then it writes **`district_severity_daily.csv`**, a 0-1 severity per district per day: 50% the GAT's predicted need, 30% flood risk, 20% vulnerability. |

**Result:** the GAT works, but with so little data it isn't better than the simple guess yet. The severity ranking still looks sensible.

---

## Step 3: Simulator and baselines (`ml/env/`, `ml/baselines/`)

### `ml/env/relief_env.py`: the simulator
Think of it as a board game that lasts 7 days:
- `reset()` sets up day 1: full stock, roads as they are.
- Each day, a strategy says *"send X of resource R from centre C to district D"*.
- `step()` checks the rules: you can't send more than you have, each centre has a limited number of truck trips (vehicles × 2), and you can't reach a district if all roads to it are blocked. It delivers what it can, scores the day, then applies the next day's road closures (recomputing shortest routes with `networkx`).
- Food, water and medicine get used up. Rescue teams can be sent somewhere new each day.

### `ml/env/metrics.py`: the scorecard
After the 7 days it reports: % of demand met, worst-off district, **Gini** (0 = perfectly even), average delivery time, and "neglected" days (a badly hit district got under 25%).

### `ml/baselines/policies.py`: four strategies
| Strategy | How it decides |
|---|---|
| Local-first | each centre helps its own district, then the nearest |
| Greedy by severity | worst-hit district first, supplied from the closest centres |
| LP: max coverage | a maths optimiser (**OR-Tools**) finds the split that meets the most need today |
| LP: fairness-aware | the same, but it also rewards helping vulnerable and severe districts and lifting the worst-off one |

### `ml/baselines/evaluate.py`
Plays all four through the 7 days and writes the comparison table to `results/baseline_report.md`.

**Result:** the optimisers are best (about 68% of need met, fairly even), but they only think about today. They run out of stock by day 5. That's the problem the Step 4 AI agents need to solve.

---

## How to run everything

```
pip install -r requirements.txt
python scripts/simulate_relief_data.py
python -m ml.nlp.train_classifier
python -m ml.nlp.extract_reports
python -m ml.gnn.train
python -m ml.baselines.evaluate
```
