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
    "coconut": "kelapa", "satay": "sate", "tea": "teh", "coffee": "kopi",
    "mie": "mi", "kol": "kubis", "ketimun": "timun", "cabe": "cabai", "lombok": "cabai",
    "telor": "telur", "pork": "babi", "lamb": "kambing",
}

MODIFIERS = {
    "goreng", "rebus", "bakar", "kukus", "panggang", "masakan", "segar", "sayur", "tumis",
    "orek", "lalapan", "semur", "manis", "pedas", "balado", "mentah", "masak", "kering",
    "bumbu", "kuah", "santan", "putih", "tim", "kampung", "ras",
}
COOKING = {"goreng", "rebus", "bakar", "kukus", "panggang", "tumis"}
PROCESSED = {"kerupuk", "keripik", "sagu", "tepung", "kue", "saos", "sari", "bubuk", "abon", "rempeyek"}
ORGANS = {"usus", "ampela", "hati", "kulit", "dideh", "darah", "jeroan", "otak", "paru",
          "babat", "limpa", "jantung", "ceker", "kepala"}
_STOP = {"dan", "dengan", "and", "with", "the", "a", "of"}


def tokens(text):
    words = re.findall(r"[a-z]+", text.lower())
    words = [w for w in words if len(w) > 1]
    return [SYNONYMS.get(w, w) for w in words if w not in _STOP]


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
        r["_order"] = tokens(r["name"].split("(")[0])
        r["_main"] = set(r["_order"])
    return rows


CONFIDENT = 0.7


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
                     "_bonus": 0.15})
    return rows


def _score(wanted, flat, food):
    """How well one food fits the words we were given (about 0 to 1.2)."""
    cand = food["_tokens"]
    heads = {w for w in wanted if w not in MODIFIERS} or wanted
    head_hit = len(heads & cand) / len(heads)
    if head_hit == 0:
        return 0.0
    weights = {w: (0.3 if w in MODIFIERS else 1.0) for w in wanted}
    overlap = sum(weights[w] for w in wanted if w in cand) / sum(weights.values())
    ratio = difflib.SequenceMatcher(None, flat, " ".join(sorted(cand))).ratio()
    score = 0.7 * overlap + 0.3 * ratio
    score *= 0.5 + 0.5 * head_hit                                     # a missing main word hurts
    extra = food.get("_main", cand) - wanted
    score -= sum(0.01 if w in MODIFIERS else 0.05 for w in extra) 
    if extra & (ORGANS | PROCESSED) and not wanted & (ORGANS | PROCESSED):
        score -= 0.3
    if wanted & COOKING:
        if not (wanted & COOKING) & cand:
            score *= 0.8
        if "mentah" in cand:
            score -= 0.3
    if set(food.get("_order", [])[:len(wanted)]) == wanted:       # name starts with exactly these words
        score += 0.08
    return score + food.get("_bonus", 0)


def suggest(name, foods, limit=5, alt=None):
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
        best = max(_score(w, f, r) for w, f in readings)
        if best > 0:
            scored.append((best, r))
    scored.sort(key=lambda s: round(s[0], 3), reverse=True)    # stable: ties keep catalog order
    return scored[:limit]