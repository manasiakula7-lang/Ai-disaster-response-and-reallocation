"""Train the baseline crisis-tweet classifier on HumAID Kerala Floods 2018.

TF-IDF (word 1-2 grams + character 2-5 grams) with a class-balanced logistic
regression. C is tuned on the dev split by macro-F1; the final model is
evaluated once on test.

Usage: python -m ml.nlp.train_classifier
Outputs: ml/nlp/models/tweet_classifier.joblib, ml/nlp/results/classifier_report.md
"""
import csv
import re
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.pipeline import FeatureUnion, Pipeline

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "raw" / "humaid_kerala_2018"
MODEL_DIR = ROOT / "ml" / "nlp" / "models"
RESULTS_DIR = ROOT / "ml" / "nlp" / "results"

URL = re.compile(r"https?://\S+")
MENTION = re.compile(r"@\w+")


def clean(text):
    text = URL.sub(" URL ", text)
    text = MENTION.sub(" USER ", text)
    text = text.replace("#", " ")
    return re.sub(r"\s+", " ", text).strip().lower()


def load(split):
    with open(DATA / f"{split}.csv", newline="", encoding="utf8") as f:
        rows = list(csv.DictReader(f))
    return [clean(r["tweet_text"]) for r in rows], [r["class_label"] for r in rows]


def build(C):
    features = FeatureUnion([
        ("word", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=3,
                                 sublinear_tf=True, max_features=60000)),
    ])
    clf = LogisticRegression(C=C, class_weight="balanced", max_iter=3000)
    return Pipeline([("features", features), ("clf", clf)])


def main():
    Xtr, ytr = load("train")
    Xdv, ydv = load("dev")
    Xte, yte = load("test")

    best = None
    for C in [0.05, 0.1, 0.2, 0.3, 0.5, 1, 2, 5]:
        model = build(C).fit(Xtr, ytr)
        f1 = f1_score(ydv, model.predict(Xdv), average="macro")
        print(f"C={C:<4} dev macro-F1={f1:.4f}")
        if best is None or f1 > best[1]:
            best = (C, f1)
    C, dev_f1 = best
    print(f"Best C={C} (dev macro-F1={dev_f1:.4f}); refitting on train+dev")

    model = build(C).fit(Xtr + Xdv, ytr + ydv)
    pred = model.predict(Xte)
    macro = f1_score(yte, pred, average="macro")
    weighted = f1_score(yte, pred, average="weighted")
    acc = accuracy_score(yte, pred)
    report = classification_report(yte, pred, digits=3)
    print(report)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_DIR / "tweet_classifier.joblib", compress=3)
    (RESULTS_DIR / "classifier_report.md").write_text(
        "# Tweet classifier: TF-IDF + logistic regression\n\n"
        f"Tuned C={C} on dev (macro-F1 {dev_f1:.3f}), refit on train+dev, evaluated on test.\n\n"
        f"| Metric (test, n={len(yte)}) | Value |\n|---|---|\n"
        f"| Macro-F1 | {macro:.3f} |\n| Weighted-F1 | {weighted:.3f} |\n| Accuracy | {acc:.3f} |\n\n"
        "```\n" + report + "```\n")
    print(f"test macro-F1={macro:.4f} weighted-F1={weighted:.4f} acc={acc:.4f}")


if __name__ == "__main__":
    main()
