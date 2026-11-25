"""Save a reviewed photo meal into the database."""
import re

from import_micros import MICRO_KEYS


def food_label(food, taken):
    """The text shown in the search box. Your own foods keep their plain name; a catalog food
    with the same name gets its code added so the two can never be mixed up."""
    name = food["name"].strip()
    if name.lower() in taken:
        name = f"{name} [{food['food_id']}]"
    taken.add(name.lower())
    return name


def label_map(all_foods):
    """(labels in order, {label lower-case: food}) for a list of foods (yours first)."""
    taken, labels, lookup = set(), [], {}
    for f in all_foods:
        label = food_label(f, taken)
        labels.append(label)
        lookup[label.lower()] = f
    return labels, lookup


def find_food(text, lookup, by_id):
    """What the person typed or picked -> a food, or None."""
    text = (text or "").strip()
    if text.lower() in lookup:
        return lookup[text.lower()]
    m = re.search(r"\[((?:tkpi|myfcd)_\d{4}|ing_\d+)\]\s*$", text, re.I)
    return by_id.get(m.group(1).lower()) if m else None


def ingredient_for(conn, food):
    """The ingredient row for a food (created from the catalog on first use, with its
    micronutrients, so vitamins and minerals count too)."""
    if food["food_id"].startswith("ing_"):
        return int(food["food_id"][4:])
    found = conn.execute("SELECT id FROM ingredients WHERE source LIKE ?",
                         (f"%{food['food_id']}%",)).fetchone()
    if found:
        return found["id"]
    name = food["name"]
    if conn.execute("SELECT 1 FROM ingredients WHERE name = ? COLLATE NOCASE", (name,)).fetchone():
        name = f"{name} [{food['food_id']}]"
    cur = conn.execute(
        "INSERT INTO ingredients (name, kcal_per_100g, protein_per_100g, carbs_per_100g, "
        "fat_per_100g, source) VALUES (?, ?, ?, ?, ?, ?)",
        (name, float(food["kcal"] or 0), float(food["protein_g"] or 0),
         float(food["carbs_g"] or 0), float(food["fat_g"] or 0),
         f"{food['source']} {food['food_id']} via food-nutrition"))
    ingredient_id = cur.lastrowid
    imputed = set((food.get("imputed_fields") or "").split(";"))
    for key in MICRO_KEYS:
        if (food.get(key) or "") != "":
            conn.execute("INSERT INTO ingredient_micros (ingredient_id, nutrient, per_100g, imputed) "
                         "VALUES (?, ?, ?, ?)",
                         (ingredient_id, key, float(food[key]), 1 if key in imputed else 0))
    return ingredient_id


def per100_dish(conn, ingredient_id, name):
    """One reusable dish per food, defined as 100 g of it. Logging 150 g = 1.5 servings, so
    saving a new photo never changes meals you logged earlier."""
    row = conn.execute("""SELECT d.id FROM dishes d JOIN dish_ingredients di ON di.dish_id = d.id
                          WHERE d.notes = 'photo' AND di.ingredient_id = ? AND di.grams = 100
                          AND (SELECT COUNT(*) FROM dish_ingredients x WHERE x.dish_id = d.id) = 1
                          ORDER BY d.id LIMIT 1""", (ingredient_id,)).fetchone()
    if row:
        return row["id"]
    label, n = f"{name} (per 100 g)", 1
    while conn.execute("SELECT 1 FROM dishes WHERE name = ?", (label,)).fetchone():
        n += 1
        label = f"{name} (per 100 g) {n}"
    cur = conn.execute("INSERT INTO dishes (name, serving_label, notes) VALUES (?, '100 g', 'photo')",
                       (label,))
    conn.execute("INSERT INTO dish_ingredients (dish_id, ingredient_id, grams) VALUES (?, ?, 100)",
                 (cur.lastrowid, ingredient_id))
    return cur.lastrowid


def save_items(conn, items, eaten_at, meal_type):
    """items = [{'food': food-dict, 'grams': float}]. One log entry per distinct food.
    Returns the number of entries written."""
    merged = {}
    for it in items:
        fid = it["food"]["food_id"]
        if fid in merged:
            merged[fid]["grams"] += it["grams"]
        else:
            merged[fid] = {"food": it["food"], "grams": it["grams"]}
    for it in merged.values():
        ing = ingredient_for(conn, it["food"])
        dish_id = per100_dish(conn, ing, it["food"]["name"])
        conn.execute("INSERT INTO meal_log (eaten_at, meal_type, dish_id, servings) VALUES (?, ?, ?, ?)",
                     (eaten_at.strftime("%Y-%m-%d %H:%M"), meal_type, dish_id, round(it["grams"] / 100.0, 3)))
    return len(merged)