from database import get_connection, init_db

init_db()

# name, kcal, protein, carbs, fat (all per 100 g). TEST VALUES ONLY.
ingredients = [
    ("Nasi putih", 130, 2.7, 28.0, 0.3),
    ("Minyak goreng", 884, 0, 0, 100),
    ("Telur ayam", 143, 12.6, 0.7, 9.5),
    ("Kecap manis", 250, 3.0, 58.0, 0.1),
]

# ingredient name, grams in one serving
recipe = [
    ("Nasi putih", 200),
    ("Minyak goreng", 10),
    ("Telur ayam", 55),
    ("Kecap manis", 10),
]

QUERY = """
SELECT d.name,
       ROUND(SUM(i.kcal_per_100g    * di.grams / 100.0), 1) AS kcal,
       ROUND(SUM(i.protein_per_100g * di.grams / 100.0), 1) AS protein,
       ROUND(SUM(i.carbs_per_100g   * di.grams / 100.0), 1) AS carbs,
       ROUND(SUM(i.fat_per_100g     * di.grams / 100.0), 1) AS fat
FROM dishes d
JOIN dish_ingredients di ON di.dish_id = d.id
JOIN ingredients i ON i.id = di.ingredient_id
GROUP BY d.id
"""

with get_connection() as conn:
    for name, kcal, p, c, f in ingredients:
        conn.execute(
            "INSERT OR IGNORE INTO ingredients "
            "(name, kcal_per_100g, protein_per_100g, carbs_per_100g, fat_per_100g, source) "
            "VALUES (?, ?, ?, ?, ?, 'test value')",
            (name, kcal, p, c, f),
        )

    conn.execute(
        "INSERT OR IGNORE INTO dishes (name, serving_label) "
        "VALUES ('Nasi goreng', '1 piring')"
    )
    dish_id = conn.execute(
        "SELECT id FROM dishes WHERE name = 'Nasi goreng'"
    ).fetchone()["id"]

    for name, grams in recipe:
        ing_id = conn.execute(
            "SELECT id FROM ingredients WHERE name = ?", (name,)
        ).fetchone()["id"]
        conn.execute(
            "INSERT OR REPLACE INTO dish_ingredients (dish_id, ingredient_id, grams) "
            "VALUES (?, ?, ?)",
            (dish_id, ing_id, grams),
        )

    for r in conn.execute(QUERY).fetchall():
        print(f"{r['name']}: {r['kcal']} kcal | "
              f"P {r['protein']} g | C {r['carbs']} g | F {r['fat']} g")