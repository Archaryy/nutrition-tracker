"""Attach micronutrients from foods.csv to the ingredients already in the database.

Run after import_data.py:  python import_micros.py
Ingredients are matched through the code in their source text (AP001, tkpi_0395,
myfcd_0001). Ingredients from pack labels have no code and simply get no micronutrients.
"""
import csv
import re
import sys

from database import get_connection, init_db

MICRO_KEYS = ["fiber_g", "calcium_mg", "iron_mg", "zinc_mg", "magnesium_mg",
              "vitamin_c_mg", "sodium_mg", "potassium_mg", "phosphorus_mg", "vitamin_b1_mg",
              "vitamin_b2_mg", "niacin_mg", "vitamin_b6_mg", "vitamin_b12_mcg",
              "cholesterol_mg", "saturated_fat_g", "sugars_total_g"]


def read(path):
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        sys.exit(f"{path} not found. Run build_foods.py first.")


def main():
    foods = read("foods.csv")
    by_id = {r["food_id"].lower(): r for r in foods}
    by_tkpi_name = {r["name"].strip().lower(): r for r in foods if r["source"] == "TKPI"}
    code_to_food = {}
    for r in read("tkpi.csv"):
        food = by_tkpi_name.get(r["name"].strip().lower())
        if food:
            code_to_food[r["code"].upper()] = food

    init_db()
    matched = rows = 0
    with get_connection() as conn:
        for ing in conn.execute("SELECT id, name, source FROM ingredients").fetchall():
            source = ing["source"] or ""
            m = re.search(r"\b(tkpi_\d{4}|myfcd_\d{4})\b", source, re.I)
            food = by_id.get(m.group(1).lower()) if m else None
            if food is None:
                m = re.search(r"\b([A-Z]{2}\d{3})\b", source)
                food = code_to_food.get(m.group(1)) if m else None
            if food is None:
                continue
            matched += 1
            imputed = set(food["imputed_fields"].split(";"))
            conn.execute("DELETE FROM ingredient_micros WHERE ingredient_id = ?", (ing["id"],))
            for key in MICRO_KEYS:
                if food.get(key, "") == "":
                    continue
                conn.execute(
                    "INSERT INTO ingredient_micros (ingredient_id, nutrient, per_100g, imputed) "
                    "VALUES (?, ?, ?, ?)",
                    (ing["id"], key, float(food[key]), 1 if key in imputed else 0))
                rows += 1
    print(f"Micronutrients added for {matched} ingredients ({rows} values).")


if __name__ == "__main__":
    main()
