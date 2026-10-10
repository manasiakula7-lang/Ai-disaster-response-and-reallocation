"""Rule-based extraction of resource needs and urgency from crisis text.

Resource types match the allocation model: food, water, medicine, rescue,
plus shelter (displacement). Urgency combines the classifier's humanitarian
category with explicit urgency cues in the text.
"""
import re

RESOURCE_KEYWORDS = {
    "food": ["food", "rice", "meal", "meals", "hungry", "starving", "ration", "rations",
             "biscuit", "biscuits", "milk", "baby food", "groceries", "provisions"],
    "water": ["drinking water", "food and water", "food or water", "water and food", "food, water", "water, food", "water bottle", "water bottles", "bottled water", "clean water",
              "potable water", "no water", "need water", "water supply"],
    "medicine": ["medicine", "medicines", "medical", "doctor", "doctors", "insulin", "first aid",
                 "ambulance", "injured", "hospital", "dialysis", "pregnant", "sanitary",
                 "napkins", "antibiotics", "fever"],
    "rescue": ["rescue", "rescued", "stranded", "trapped", "stuck", "boat", "boats", "helicopter",
               "airlift", "evacuate", "evacuation", "sos", "marooned", "roof", "rooftop",
               "terrace", "ndrf", "navy", "army"],
    "shelter": ["shelter", "relief camp", "relief camps", "camp", "camps", "homeless",
                "displaced", "blanket", "blankets", "clothes", "mats", "bedsheets"],
}

URGENCY_CUES = ["urgent", "urgently", "emergency", "sos", "asap", "immediately", "please help",
                "help needed", "need help", "trapped", "stranded", "no food", "no water",
                "dying", "critical", "elderly", "old age", "bedridden", "children", "kids",
                "pregnant", "baby", "infant", "since yesterday", "for 2 days", "for two days",
                "no response", "water level rising", "water rising", "first floor", "roof"]

PHONE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")

# How much each HumAID category implies an actionable need on its own.
CLASS_URGENCY = {
    "requests_or_urgent_needs": 0.6,
    "displaced_people_and_evacuations": 0.5,
    "injured_or_dead_people": 0.5,
    "infrastructure_and_utility_damage": 0.35,
    "caution_and_advice": 0.2,
    "rescue_volunteering_or_donation_effort": 0.15,
    "other_relevant_information": 0.1,
    "sympathy_and_support": 0.0,
    "not_humanitarian": 0.0,
}

# Default resource implied by a category when the text names none.
CLASS_DEFAULT_RESOURCE = {
    "displaced_people_and_evacuations": "shelter",
    "injured_or_dead_people": "medicine",
    "infrastructure_and_utility_damage": "rescue",
}

_RES_PATTERNS = {
    res: [re.compile(r"(?<![a-z])" + re.escape(k) + r"(?![a-z])") for k in kws]
    for res, kws in RESOURCE_KEYWORDS.items()
}


def find_resources(text, label=None):
    t = text.lower()
    found = [res for res, pats in _RES_PATTERNS.items() if any(p.search(t) for p in pats)]
    if not found and label in CLASS_DEFAULT_RESOURCE:
        found = [CLASS_DEFAULT_RESOURCE[label]]
    return found


def urgency_score(text, label, label_prob=1.0):
    """0-1 score: category prior (weighted by classifier confidence) plus text cues."""
    t = text.lower()
    score = CLASS_URGENCY.get(label, 0.0) * label_prob
    cues = sum(1 for c in URGENCY_CUES if c in t)
    score += min(0.3, 0.1 * cues)
    if PHONE.search(text):
        score += 0.1  # a contact number usually means a specific, actionable request
    if label in ("sympathy_and_support", "not_humanitarian"):
        score = min(score, 0.2)
    return round(min(1.0, score), 3)
