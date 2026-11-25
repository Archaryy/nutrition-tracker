"""Learn from your corrections. """

from statistics import median

from food_match import tokens

KEEP = 10

def key_for(text):
    """'Ayam Goreng' and 'goreng ayam' are the same thing."""
    return " ".join(sorted(set(tokens(text or ""))))


def remember(conn, seen, food_id, food_name, grams):
    key = key_for(seen)
    if key and food_id and grams > 0:
        conn.execute("INSERT INTO photo_feedback (seen_key, food_id, food_name, grams) "
                     "VALUES (?, ?, ?, ?)", (key, food_id, food_name, grams))


def recall(conn, seen):
    """What you usually chose for this name: {'food_id', 'food_name', 'grams', 'n'} or None."""
    key = key_for(seen)
    if not key:
        return None
    rows = conn.execute("SELECT food_id, food_name, grams FROM photo_feedback "
                        "WHERE seen_key = ? ORDER BY id DESC LIMIT ?", (key, KEEP)).fetchall()
    if not rows:
        return None
    counts = {}
    for r in rows:
        counts[r["food_id"]] = counts.get(r["food_id"], 0) + 1
    best = max(counts, key=lambda f: (counts[f], -[r["food_id"] for r in rows].index(f)))
    mine = [r for r in rows if r["food_id"] == best]
    return {"food_id": best, "food_name": mine[0]["food_name"],
            "grams": round(median(r["grams"] for r in mine)), "n": len(mine)}


def usual_foods(conn, limit=20):
    """Names of the foods you pick most often. They are shown to the model as hints."""
    rows = conn.execute("SELECT food_name, COUNT(*) AS n FROM photo_feedback "
                        "GROUP BY food_id ORDER BY n DESC, MAX(id) DESC LIMIT ?", (limit,))
    return [r["food_name"] for r in rows]