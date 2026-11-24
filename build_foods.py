"""Build foods.csv from the food-nutrition repo (intanypurbasari/food-nutrition).

Usage:  python build_foods.py ../food-nutrition

foods.csv holds every TKPI and MyFCD food with macros, micronutrients and honest flags:
  macros_imputed  yes if any of kcal/protein/carbs/fat was filled in by the repo's
                  imputation (a group average, not a measurement)
  imputed_micros  how many micronutrient values were imputed rather than measured
"""
import csv
import os
import sys

MACROS = {"energy_kcal": "kcal", "protein_g": "protein_g",
          "carbohydrate_g": "carbs_g", "fat_g": "fat_g"}
MICROS = ["fiber_g", "calcium_mg", "phosphorus_mg", "iron_mg", "sodium_mg", "potassium_mg",
          "zinc_mg", "magnesium_mg", "vitamin_c_mg", "vitamin_b1_mg", "vitamin_b2_mg",
          "niacin_mg", "vitamin_b6_mg", "vitamin_b12_mcg", "cholesterol_mg",
          "saturated_fat_g", "sugars_total_g"]
OUT = "foods.csv"


def read(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def blank(v):
    return v is None or str(v).strip() == ""


def tidy(name, source):
    name = name.strip()
    if source == "TKPI" and name.endswith(")") and " (" in name:
        name = name[: name.rindex(" (")]          # drop the English gloss
    return name.title() if name.isupper() else name


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    data = os.path.join(sys.argv[1], "data_processed")
    final = read(os.path.join(data, "nutrition_repository_imputed.csv"))
    observed = {}
    for fname in ("tkpi_enriched.csv", "myfcd_enriched.csv"):
        for r in read(os.path.join(data, fname)):
            observed[r["food_id"]] = r

    columns = (["food_id", "name", "source", "category", "kcal", "protein_g", "carbs_g",
                "fat_g", "macros_imputed", "imputed_micros"] + MICROS)
    rows = []
    for r in final:
        obs = observed.get(r["food_id"], {})
        imputed_macro = any(blank(obs.get(k)) for k in MACROS)
        imputed_micro = sum(1 for k in MICROS if blank(obs.get(k)))
        row = {"food_id": r["food_id"], "name": tidy(r["food_name_original"], r["source"]),
               "source": r["source"], "category": r["category_normalized"],
               "macros_imputed": "yes" if imputed_macro else "no",
               "imputed_micros": imputed_micro}
        for src, dst in MACROS.items():
            row[dst] = round(float(r[src]), 1) if not blank(r[src]) else ""
        for k in MICROS:
            row[k] = round(float(r[k]), 3) if not blank(r[k]) else ""
        rows.append(row)

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)
    safe = sum(1 for r in rows if r["macros_imputed"] == "no")
    print(f"Wrote {len(rows)} foods to {OUT}; {safe} have fully measured macros, "
          f"{len(rows) - safe} have imputed macros.")


if __name__ == "__main__":
    main()
