import csv
import math
import sys

from database import get_connection, init_db, dish_totals

INGREDIENT_COLUMNS = ["name", "kcal", "protein_g", "carbs_g", "fat_g", "source"]
RECIPE_COLUMNS = ["dish", "serving_label", "ingredient", "grams"]


def read_rows(path, required):
    """Read a CSV. Works with comma or semicolon files (Indonesian Excel uses ;)."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        header = f.readline()
        delimiter = ";" if header.count(";") > header.count(",") else ","
        f.seek(0)
        reader = csv.DictReader(f, delimiter=delimiter)
        reader.fieldnames = [h.strip() for h in (reader.fieldnames or [])]
        missing = [c for c in required if c not in reader.fieldnames]
        if missing:
            raise SystemExit(f"{path}: missing column(s): {', '.join(missing)}")
        return list(reader)


def number(value, where):
    """Turn text like '12.5' or '12,5' into a float, or explain what is wrong."""
    try:
        n = float(value.strip().replace(",", "."))
    except (ValueError, AttributeError):
        raise ValueError(f"{where} is not a number: {value!r} (type 0 for trace amounts)")
    if not math.isfinite(n) or n < 0:
        raise ValueError(f"{where} must be 0 or more, got {value!r}")
    return n


UPSERT_INGREDIENT = """
INSERT INTO ingredients
    (name, kcal_per_100g, protein_per_100g, carbs_per_100g, fat_per_100g, source)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT(name) DO UPDATE SET
    kcal_per_100g    = excluded.kcal_per_100g,
    protein_per_100g = excluded.protein_per_100g,
    carbs_per_100g   = excluded.carbs_per_100g,
    fat_per_100g     = excluded.fat_per_100g,
    source           = excluded.source
"""


def import_ingredients(conn, path, errors, warnings):
    count = 0
    for line, row in enumerate(read_rows(path, INGREDIENT_COLUMNS), start=2):
        name = (row["name"] or "").strip()
        if not name:
            errors.append(f"{path} line {line}: the name is empty")
            continue
        where = f"{path} line {line} ({name})"
        try:
            kcal = number(row["kcal"], f"{where} kcal")
            protein = number(row["protein_g"], f"{where} protein_g")
            carbs = number(row["carbs_g"], f"{where} carbs_g")
            fat = number(row["fat_g"], f"{where} fat_g")
        except ValueError as e:
            errors.append(str(e))
            continue

        # Sanity check: kcal should be close to 4*protein + 4*carbs + 9*fat.
        # Fibre and alcohol cause small gaps, so this only warns.
        expected = 4 * protein + 4 * carbs + 9 * fat
        if abs(kcal - expected) > max(25, 0.15 * kcal):
            warnings.append(
                f"{where}: kcal is {kcal:g} but protein/carbs/fat add up to about "
                f"{expected:.0f}. Check for a typo."
            )

        source = (row["source"] or "").strip()
        conn.execute(UPSERT_INGREDIENT, (name, kcal, protein, carbs, fat, source))
        count += 1
    return count


def import_recipes(conn, path, errors):
    dishes = {}  # dish name -> {"label": ..., "items": {ingredient_id: grams}}
    for line, row in enumerate(read_rows(path, RECIPE_COLUMNS), start=2):
        dish = (row["dish"] or "").strip()
        ingredient = (row["ingredient"] or "").strip()
        if not dish or not ingredient:
            errors.append(f"{path} line {line}: dish and ingredient are both required")
            continue

        found = conn.execute(
            "SELECT id FROM ingredients WHERE name = ? COLLATE NOCASE", (ingredient,)
        ).fetchone()
        if found is None:
            errors.append(
                f"{path} line {line}: unknown ingredient {ingredient!r} in {dish!r}. "
                "Spell it exactly like in ingredients.csv."
            )
            continue

        try:
            grams = number(row["grams"], f"{path} line {line} ({dish}) grams")
        except ValueError as e:
            errors.append(str(e))
            continue
        if grams == 0:
            errors.append(f"{path} line {line} ({dish}): grams must be above 0")
            continue

        label = (row["serving_label"] or "").strip() or "1 porsi"
        entry = dishes.setdefault(dish, {"label": label, "items": {}})
        if found["id"] in entry["items"]:
            errors.append(f"{path} line {line}: {ingredient!r} appears twice in {dish!r}")
            continue
        entry["items"][found["id"]] = grams

    if errors:
        return 0

    for dish, entry in dishes.items():
        conn.execute(
            "INSERT INTO dishes (name, serving_label) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET serving_label = excluded.serving_label",
            (dish, entry["label"]),
        )
        dish_id = conn.execute(
            "SELECT id FROM dishes WHERE name = ?", (dish,)
        ).fetchone()["id"]
        # The CSV is the source of truth: replace the old ingredient list.
        conn.execute("DELETE FROM dish_ingredients WHERE dish_id = ?", (dish_id,))
        conn.executemany(
            "INSERT INTO dish_ingredients (dish_id, ingredient_id, grams) VALUES (?, ?, ?)",
            [(dish_id, ing_id, grams) for ing_id, grams in entry["items"].items()],
        )
    return len(dishes)


def main():
    ingredients_path = sys.argv[1] if len(sys.argv) > 1 else "ingredients.csv"
    recipes_path = sys.argv[2] if len(sys.argv) > 2 else "recipes.csv"

    init_db()
    errors, warnings = [], []
    conn = get_connection()
    n_ingredients = n_dishes = 0
    try:
        with conn:  # commits on success, undoes everything on an error
            n_ingredients = import_ingredients(conn, ingredients_path, errors, warnings)
            if not errors:
                n_dishes = import_recipes(conn, recipes_path, errors)
            if errors:
                raise RuntimeError("validation failed")
    except FileNotFoundError as e:
        sys.exit(f"File not found: {e.filename}. Run this from the folder that contains it.")
    except RuntimeError:
        print("Nothing was imported. Fix these problems and run again:\n")
        for message in errors:
            print(" -", message)
        sys.exit(1)

    print(f"Imported {n_ingredients} ingredients and {n_dishes} dishes.")
    for message in warnings:
        print("WARNING:", message)
    print("\nPer serving:")
    for r in dish_totals(conn):
        print(f"  {r['name']} ({r['serving_label']}): {r['kcal']} kcal | "
              f"P {r['protein']} g | C {r['carbs']} g | F {r['fat']} g")
    conn.close()


if __name__ == "__main__":
    main()