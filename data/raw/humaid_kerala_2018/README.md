# HumAID: Kerala Floods 2018

Source: HumAID dataset (Alam et al., ICWSM 2021), event `kerala_floods_2018`. Columns: `tweet_id, tweet_text, class_label`.

| Split | Tweets |
|---|---|
| train | 5,588 |
| dev | 814 |
| test | 1,582 |

Classes (train): rescue_volunteering_or_donation_effort 3005, other_relevant_information 669, sympathy_and_support 585, requests_or_urgent_needs 413, not_humanitarian 319, injured_or_dead_people 254, infrastructure_and_utility_damage 207, caution_and_advice 97, displaced_people_and_evacuations 39.

Notes:
- Strongly imbalanced (54% rescue/donation), so report macro-F1, not accuracy.
- Only ~12% of tweets name a district or major town (Ernakulam/Kochi most, Kasaragod least). Location extraction needs a gazetteer of towns, not just district names.
- Tweet IDs are Twitter snowflakes, so post time = `(id >> 22) + 1288834974657` ms. Tweets span 17 Aug to 12 Sep 2018, peaking 18 Aug, which lets the reallocation loop replay them in time order.
