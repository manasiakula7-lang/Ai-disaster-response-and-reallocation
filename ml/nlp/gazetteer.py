"""Place names (districts, taluks, towns, flood-hit localities) mapped to the
14 Kerala districts, used to locate crisis tweets.

Hand-built for the 2018 floods: district names and common spellings, taluk
headquarters, and localities that were widely reported during the floods.
"""
import re

DISTRICT_ALIASES = {
    "Alappuzha": ["alappuzha", "alleppey", "alapuzha", "alappey", "kuttanad", "chengannur",
                  "cherthala", "mavelikkara", "mavelikara", "haripad", "kayamkulam",
                  "ambalappuzha", "pandanad", "edathua", "ramankary", "champakulam",
                  "kainakary", "pulinkunnu", "nedumudi", "thakazhy", "budhanoor"],
    "Ernakulam": ["ernakulam", "kochi", "cochin", "aluva", "alwaye", "paravur", "paravoor",
                  "north paravur", "kalady", "kaladi", "angamaly", "angamali", "perumbavoor",
                  "muvattupuzha", "kothamangalam", "kakkanad", "eloor", "kalamassery",
                  "edappally", "chendamangalam", "puthenvelikkara", "kunnukara", "nedumbassery",
                  "fort kochi", "vypin", "tripunithura", "piravom", "kadungalloor", "eloor"],
    "Idukki": ["idukki", "munnar", "thodupuzha", "adimali", "kattappana", "painavu",
               "cheruthoni", "nedumkandam", "devikulam", "peerumade", "peermade",
               "vandiperiyar", "kumily", "mullaperiyar", "idukki dam"],
    "Kannur": ["kannur", "cannanore", "thalassery", "tellicherry", "payyanur", "iritty",
               "taliparamba", "mattannur", "kuthuparamba"],
    "Kasaragod": ["kasaragod", "kasargod", "kasaragode", "kanhangad", "nileshwar", "manjeshwar"],
    "Kollam": ["kollam", "quilon", "karunagappally", "kottarakkara", "punalur", "paravur kollam",
               "sasthamkotta", "pathanapuram"],
    "Kottayam": ["kottayam", "changanassery", "changanacherry", "vaikom", "pala", "kumarakom",
                 "ettumanoor", "kanjirappally", "erumely", "kuravilangad", "thiruvarppu"],
    "Kozhikode": ["kozhikode", "calicut", "vadakara", "koyilandy", "thamarassery", "mukkam",
                  "kuttiady", "feroke", "kodiyathur"],
    "Malappuram": ["malappuram", "manjeri", "nilambur", "perinthalmanna", "tirur", "ponnani",
                   "kondotty", "tirurangadi", "kottakkal", "areekode", "vazhakkad"],
    "Palakkad": ["palakkad", "palghat", "ottapalam", "mannarkkad", "mannarkad", "attappadi",
                 "chittur", "alathur", "shoranur", "nemmara", "malampuzha", "nenmara"],
    "Pathanamthitta": ["pathanamthitta", "pathanamthita", "pattanamtitta", "ranni", "aranmula",
                       "thiruvalla", "tiruvalla", "kozhencherry", "adoor", "konni", "pandalam",
                       "mallappally", "sabarimala", "pamba", "pampa", "kozhenchery", "eraviperoor",
                       "kadapra", "niranam", "parumala", "vadasserikkara", "maramon"],
    "Thiruvananthapuram": ["thiruvananthapuram", "trivandrum", "tvm", "neyyattinkara",
                           "attingal", "varkala", "nedumangad", "kovalam", "vizhinjam"],
    "Thrissur": ["thrissur", "trichur", "chalakudy", "chalakudi", "kodungallur",
                 "irinjalakuda", "guruvayur", "kunnamkulam", "wadakkanchery", "mala",
                 "annamanada", "pariyaram", "athirappilly", "athirapally", "kuzhur",
                 "chavakkad", "kodakara"],
    "Wayanad": ["wayanad", "wynad", "kalpetta", "kalpatta", "mananthavady", "sulthan bathery",
                "sultan bathery", "vythiri", "meppadi", "panamaram"],
}

# Ambiguous words that are also common English or used outside Kerala.
_REQUIRE_CONTEXT = {"pala", "mala", "pamba", "pampa"}

_PATTERNS = [
    (district, alias, re.compile(r"(?<![a-z])" + re.escape(alias) + r"(?![a-z])"))
    for district, aliases in DISTRICT_ALIASES.items()
    for alias in sorted(set(aliases), key=len, reverse=True)
]


def find_districts(text):
    """Return districts mentioned in text, most-mentioned first ([] if none)."""
    t = text.lower().replace("#", " ")
    counts = {}
    for district, alias, pat in _PATTERNS:
        if alias in _REQUIRE_CONTEXT and "kerala" not in t and district.lower() not in t:
            continue
        n = len(pat.findall(t))
        if n:
            counts[district] = counts.get(district, 0) + n
    return sorted(counts, key=counts.get, reverse=True)
