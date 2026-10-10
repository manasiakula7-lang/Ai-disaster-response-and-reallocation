# Tweet classifier: TF-IDF + logistic regression

Tuned C=0.5 on dev (macro-F1 0.608), refit on train+dev, evaluated on test.

| Metric (test, n=1582) | Value |
|---|---|
| Macro-F1 | 0.595 |
| Weighted-F1 | 0.716 |
| Accuracy | 0.705 |

```
                                        precision    recall  f1-score   support

                    caution_and_advice      0.405     0.536     0.462        28
      displaced_people_and_evacuations      0.556     0.455     0.500        11
     infrastructure_and_utility_damage      0.565     0.593     0.579        59
                injured_or_dead_people      0.806     0.806     0.806        72
                      not_humanitarian      0.339     0.478     0.396        90
            other_relevant_information      0.424     0.444     0.434       189
              requests_or_urgent_needs      0.543     0.812     0.651       117
rescue_volunteering_or_donation_effort      0.912     0.778     0.840       851
                  sympathy_and_support      0.670     0.715     0.692       165

                              accuracy                          0.705      1582
                             macro avg      0.580     0.624     0.595      1582
                          weighted avg      0.739     0.705     0.716      1582
```
