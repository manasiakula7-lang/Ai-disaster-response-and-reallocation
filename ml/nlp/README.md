# Step 1: NLP demand detection

Turns crisis tweets into located, typed, scored demand signals.

```
python -m ml.nlp.train_classifier   # trains + evaluates the classifier
python -m ml.nlp.extract_reports    # tags every tweet, writes the outputs below
```

| Module | What it does |
|---|---|
| `train_classifier.py` | TF-IDF (word 1-2 + char 2-5 grams) + class-balanced logistic regression over the 9 HumAID categories. C tuned on dev, refit on train+dev, tested once. |
| `gazetteer.py` | ~200 district names, spellings, taluks and flood-hit localities (Chengannur, Kuttanad, Aluva, Chalakudy, Ranni...) mapped to the 14 districts. |
| `needs.py` | Keyword rules for resource needs (food, water, medicine, rescue, shelter) and an urgency score from the predicted category, its confidence, urgency cues ("trapped", "no food", "elderly"...) and contact numbers. |
| `extract_reports.py` | Applies all three to every tweet; derives post time from the tweet ID. |

## Outputs

- `data/processed/crisis_reports.csv`: one row per tweet (7,984): time, predicted and gold label, districts, resources, urgency, actionable flag.
- `data/processed/district_daily_signals.csv`: date × district: report counts and urgency-weighted need per resource. This is the NLP input to the GAT (Step 2) and the live feed for reallocation (Step 6).

## Results (test split, n=1,582)

| Metric | Value |
|---|---|
| Classifier macro-F1 | 0.595 |
| Classifier weighted-F1 / accuracy | 0.716 / 0.705 |
| `requests_or_urgent_needs` recall | 0.81 |
| Urgency score AUROC for spotting gold urgent requests | 0.905 |
| Precision of the 100 most urgent tweets (gold urgent requests) | 0.60 |
| Tweets located to a district | 14.0% (1,115) |

Full per-class report: `results/classifier_report.md`.

## Known limits

- Only 14% of tweets name a place, so district signals are sparse (Ernakulam and Alappuzha dominate, Kasaragod has 11 reports). The GAT should treat them as one feature among several, not ground truth.
- The gazetteer can't tell where help is *needed* from where it is *coming from* ("fishermen from Kollam moving to affected areas").
- Smallest classes are weak (displaced people: 11 test tweets, F1 0.50).
- Upgrade path: fine-tune DistilBERT/XLM-R on Colab (HumAID papers report macro-F1 around 0.7 with BERT-family models); the rest of the pipeline only needs `predict_proba`.
