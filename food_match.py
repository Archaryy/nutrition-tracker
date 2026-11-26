"""Match a food name from the photo model to the closest foods in foods.csv."""
import csv
import difflib
import re

# English words a vision model sometimes uses -> the Indonesian words TKPI uses
SYNONYMS = {
    "rice": "nasi", "fried": "goreng", "chicken": "ayam", "egg": "telur", "fish": "ikan",
    "beef": "sapi", "noodle": "mi", "noodles": "mi", "vegetable": "sayur", "vegetables": "sayur",
    "spinach": "bayam", "tofu": "tahu", "boiled": "rebus", "grilled": "bakar",
    "soup": "sop", "shrimp": "udang", "potato": "kentang", "cucumber": "timun",
    "banana": "pisang", "bread": "roti", "milk": "susu",
    "white": "putih", "roasted": "panggang", "carrot": "wortel",
    "carrots": "wortel", "tempeh": "tempe", "omelette": "dadar", "omelet": "dadar",
    "cabbage": "kubis", "tomato": "tomat", "chili": "cabai", "chilli": "cabai",
    "corn": "jagung", "peanut": "kacang", "peanuts": "kacang", "cassava": "singkong",
    "sausage": "sosis", "meatball": "bakso", "meatballs": "bakso", "apple": "apel",
    "orange": "jeruk", "watermelon": "semangka", "papaya": "pepaya", "mango": "mangga",
    "coconut": "kelapa", "satay": "sate", "sate": "sate", "tea": "teh", "coffee": "kopi",
    "mie": "mi", "kol": "kubis", "ketimun": "timun", "cabe": "cabai", "lombok": "cabai",
    "telor": "telur", "pork": "babi", "lamb": "kambing",
    "breast": "dada", "thigh": "paha", "drumstick": "paha", "wing": "sayap", "wings": "sayap",
    "vermicelli": "bihun", "ramen": "mi", "pasta": "spaghetti", "spaghetti": "spaghetti",
    "instant": "instan", "crackers": "kerupuk", "cracker": "kerupuk", "chips": "keripik",
    "shrimps": "udang", "prawn": "udang", "squid": "cumi", "crab": "kepiting",
    "duck": "bebek", "goat": "kambing", "porridge": "bubur", "dumpling": "pangsit",
}
# Words that describe HOW a food is cooked or served, not WHAT it is. They count for little,
# so "ayam goreng" is mostly about "ayam" and not about "goreng".
MODIFIERS = {
    "goreng", "rebus", "bakar", "kukus", "panggang", "masakan", "segar", "sayur", "tumis",
    "orek", "lalapan", "semur", "manis", "pedas", "balado", "mentah", "masak", "kering",
    "bumbu", "kuah", "santan", "putih", "tim", "kampung", "ras", "daging", "irisan", "potong",
}
COOKING = {"goreng", "rebus", "bakar", "kukus", "panggang", "tumis"}
RAW = {"mentah", "kering"}
# Parts and organs: never suggested unless the photo model names them.
PROCESSED = {"kerupuk", "keripik", "keremes", "kremes", "emping", "sagu", "tepung", "kue", "saos", "sari", "bubuk", "abon", "rempeyek"}
ORGANS = {"usus", "ampela", "hati", "kulit", "dideh", "darah", "jeroan", "otak", "paru",
          "babat", "limpa", "jantung", "ceker", "kepala"}
_STOP = {"dan", "dengan", "and", "with", "the", "a", "of", "steamed", "cooked", "sliced", "slice",
         "slices", "piece", "pieces", "fresh", "plain", "stir", "style", "dish", "sauce"}


# Which kind of food a name is about. The photo model says what KIND of food it sees (noodle, rice,
# chicken ...); a food of a different kind is pushed down, so noodles never turn into rice or crackers.
FAMILIES = [        # order matters: "kerupuk mie" is a snack, "mie ayam" is a noodle dish
    ("snack", {"kerupuk", "keripik", "keremes", "kremes", "rempeyek", "emping", "rengginang"}),
    ("noodle", {"mi", "bihun", "kwetiau", "soun", "makaroni", "spaghetti", "laksa", "lomi"}),
    ("rice", {"nasi", "beras", "lontong", "ketupat", "bubur", "lemper"}),
    ("chicken", {"ayam"}),
    ("beef", {"sapi", "kambing", "domba", "rendang"}),
    ("pork", {"babi"}),
    ("fish", {"ikan", "udang", "cumi", "kepiting", "kerang", "lele", "tuna", "salmon", "tongkol",
              "bandeng", "teri", "sarden", "gurame", "nila", "kembung"}),
    ("egg", {"telur"}),
    ("tofu_tempeh", {"tahu", "tempe"}),
]
KIND_TO_FAMILY = {"rice": "rice", "noodle": "noodle", "chicken": "chicken", "beef": "beef",
                  "pork": "pork", "fish": "fish", "seafood": "fish", "egg": "egg",
                  "tofu_tempeh": "tofu_tempeh", "snack": "snack"}
# For kinds without a word list: which foods.csv categories fit
KIND_TO_CATEGORIES = {
    "vegetable": {"sayuran", "vegetables and vegetable products", "vegetable dishes"},
    "fruit": {"buah", "fruits and fruit products"},
    "drink": {"minuman non alkohol", "beverages", "susu", "milk and milk products"},
}


def family_of(words):
    """The family of a food from the words in its name, or None."""
    words = set(words)
    for family, keys in FAMILIES:
        if words & keys:
            return family
    return None


def tokens(text):
    words = re.findall(r"[a-z]+", text.lower())
    words = [w for w in words if len(w) > 1]
    words = [SYNONYMS.get(w, w) for w in words if w not in _STOP]
    if "nasi" in words:                       # "nasi putih" is just rice
        words = [w for w in words if w != "putih"]
    return words


def load_foods(path="foods.csv", include_imputed=False):
    """Foods from foods.csv. Foods whose calories/macros were guessed (imputed) are left out:
    a photo log should not rest on a guessed number."""
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    except FileNotFoundError:
        return []
    if not include_imputed:
        rows = [r for r in rows if r.get("macros_imputed") != "yes"]
    for r in rows:
        r["_tokens"] = set(tokens(r["name"]))
        r["_order"] = tokens(r["name"].split("(")[0])        # without the English/Malay alias
        r["_main"] = set(r["_order"])
        r["_fam"] = family_of(r["_main"])
    return rows


CONFIDENT = 0.7    # below this score a match is shown as an option but never pre-selected


def user_foods(conn):
    """Your own ingredients, shaped like foods.csv rows. They are tried before the big catalog,
    because you already chose them (for example your own 'Nasi putih')."""
    rows = []
    for r in conn.execute("SELECT id, name, kcal_per_100g, protein_per_100g, carbs_per_100g, "
                          "fat_per_100g FROM ingredients ORDER BY name"):
        rows.append({"food_id": f"ing_{r['id']}", "name": r["name"], "source": "mine",
                     "kcal": r["kcal_per_100g"], "protein_g": r["protein_per_100g"],
                     "carbs_g": r["carbs_per_100g"], "fat_g": r["fat_per_100g"],
                     "macros_imputed": "no", "imputed_fields": "", "_tokens": set(tokens(r["name"])),
                     "_main": set(tokens(r["name"])), "_order": tokens(r["name"]),
                     "_fam": family_of(tokens(r["name"])), "_bonus": 0.15})
    return rows


def _score(wanted, flat, food, kind=None):
    """How well one food fits the words we were given (about 0 to 1.2)."""
    cand = food["_tokens"]
    heads = {w for w in wanted if w not in MODIFIERS} or wanted      # the words that say WHAT it is
    head_hit = len(heads & cand) / len(heads)
    if head_hit == 0:
        return 0.0
    weights = {w: (0.3 if w in MODIFIERS else 1.0) for w in wanted}
    overlap = sum(weights[w] for w in wanted if w in cand) / sum(weights.values())
    ratio = difflib.SequenceMatcher(None, flat, " ".join(sorted(cand))).ratio()
    score = 0.7 * overlap + 0.3 * ratio
    score *= 0.5 + 0.5 * head_hit                                     # a missing main word hurts
    extra = food.get("_main", cand) - wanted
    score -= sum(0.01 if w in MODIFIERS else 0.05 for w in extra)    # long, specific names lose
    if extra & (ORGANS | PROCESSED) and not wanted & (ORGANS | PROCESSED):
        score -= 0.3
    # "ayam goreng" is not "ayam mentah" or plain "tempe": the way it was cooked changes the calories
    if wanted & COOKING:
        if not (wanted & COOKING) & cand:
            # cooked another way (fried when it was grilled) is worse than no cooking word at all
            score *= 0.6 if cand & COOKING else 0.8
    # A photo shows prepared food: dry or raw entries (dry noodles, raw rice) carry far more calories
    if cand & RAW and not wanted & RAW:
        score -= 0.25
    if set(food.get("_order", [])[:len(wanted)]) == wanted:       # name starts with exactly these words
        score += 0.08
    score += food.get("_bonus", 0)
    if "telur" in wanted and "ayam" in cand and not wanted & {"bebek", "puyuh", "itik"}:
        score += 0.02                         # a plain "telur" means a chicken egg
    # The photo model's idea of the KIND of food (noodle, rice, chicken ...)
    want_fam = KIND_TO_FAMILY.get(kind)
    if want_fam:
        fam = food.get("_fam")
        if fam == want_fam:
            score += 0.12
        elif fam:
            score *= 0.45                         # a different known kind: very unlikely
        else:
            score *= 0.75                         # no kind known (flour, oil...): unlikely
    elif kind in KIND_TO_CATEGORIES and food.get("category"):
        score *= 1.0 if food["category"] in KIND_TO_CATEGORIES[kind] else 0.7
    return score


def suggest(name, foods, limit=5, alt=None, kind=None):
    """[(score, food)] best first. `alt` is the same food in another language (the model's
    English name); the better of the two readings counts."""
    readings = []
    for text in (name, alt):
        words = tokens(text or "")
        if words:
            readings.append((set(words), " ".join(sorted(set(words)))))
    if not readings:
        return []
    scored = []
    for r in foods:
        best = max(_score(w, f, r, kind) for w, f in readings)
        if best > 0:
            scored.append((best, r))
    scored.sort(key=lambda s: round(s[0], 3), reverse=True)    # stable: ties keep catalog order
    return scored[:limit]


def search(query, foods, limit=8):
    """Type-to-search for the food picker. Every typed word must start a word in the name
    ("ayam gor" finds "Ayam goreng ..."); English words work too ("chicken" finds "Ayam ...")."""
    words = re.findall(r"[a-z0-9]+", (query or "").lower())
    if not words:
        return []
    patterns = []
    for w in words:
        p = [re.compile(r"\b" + re.escape(w))]
        if SYNONYMS.get(w, w) != w:                      # a translated word must match whole
            p.append(re.compile(r"\b" + re.escape(SYNONYMS[w]) + r"\b"))
        patterns.append(p)
    asked = set(words) | {SYNONYMS.get(w, w) for w in words}
    scored = []
    for r in foods:
        name = r["name"].lower()
        if not all(any(p.search(name) for p in group) for group in patterns):
            continue
        starts = any(p.match(name) for p in patterns[0])
        score = 2 * starts + (r.get("_bonus", 0) > 0) - len(name) / 200
        if r["_main"] & (ORGANS | PROCESSED | RAW) - asked:   # offal, crackers, raw: only if asked for
            score -= 1.5
        scored.append((score, r))
    scored.sort(key=lambda s: s[0], reverse=True)
    found = [r for _, r in scored[:limit]]
    if len(found) < limit:                            # a misspelling: fall back to fuzzy matching
        have = {r["food_id"] for r in found}
        found += [r for _, r in suggest(query, foods, limit=limit) if r["food_id"] not in have]
    return found[:limit]