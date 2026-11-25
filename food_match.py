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
}
_STOP = {"dan", "dengan", "and", "with", "the", "a", "of"}


def tokens(text):
    words = re.findall(r"[a-z]+", text.lower())
    return [SYNONYMS.get(w, w) for w in words if w not in _STOP]


def load_foods(path="foods.csv"):
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    except FileNotFoundError:
        return []
    for r in rows:
        r["_tokens"] = set(tokens(r["name"]))
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
                     "_bonus": 0.15})
    return rows


def suggest(name, foods, limit=5):
    """[(score, food)] best first. Foods with imputed macros are included but ranked lower."""
    want = tokens(name)
    if not want:
        return []
    wanted = set(want)
    flat = " ".join(want)
    scored = []
    for r in foods:
        overlap = len(wanted & r["_tokens"]) / len(wanted)
        if overlap == 0:
            continue
        ratio = difflib.SequenceMatcher(None, flat, " ".join(sorted(r["_tokens"]))).ratio()
        score = 0.65 * overlap + 0.35 * ratio
        # prefer plain, short names ("Ayam goreng") over long processed ones
        score -= 0.01 * max(len(r["_tokens"]) - len(wanted), 0)
        score += r.get("_bonus", 0)
        if r["macros_imputed"] == "yes":
            score -= 0.3
        scored.append((score, r))
    scored.sort(key=lambda s: s[0], reverse=True)
    return scored[:limit] 