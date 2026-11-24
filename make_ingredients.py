import csv
import os
import sys

TKPI_FILE = "tkpi.csv"
PICKS_FILE = "picks.txt"
OWN_FILE = "my_ingredients.csv"      # optional: foods from pack labels
OUT_FILE = "ingredients.csv"
COLUMNS = ["name", "kcal", "protein_g", "carbs_g", "fat_g", "source"]

with open(TKPI_FILE, newline="", encoding="utf-8-sig") as f:
    tkpi = {r["code"]: r for r in csv.DictReader(f)}

if not os.path.exists(PICKS_FILE):
    sys.exit(f"{PICKS_FILE} not found. Create it with lines like:  AP001 = Nasi putih")

FOODS_FILE = "foods.csv"            # built by build_foods.py (TKPI + MyFCD)
foods = {}
if os.path.exists(FOODS_FILE):
    with open(FOODS_FILE, newline="", encoding="utf-8-sig") as f:
        foods = {r["food_id"].lower(): r for r in csv.DictReader(f)}

rows, names, problems = [], set(), []


def add(name, kcal, protein, carbs, fat, source, where):
    if name.lower() in names:
        problems.append(f"{where}: the name {name!r} is used twice")
        return
    names.add(name.lower())
    rows.append([name, kcal, protein, carbs, fat, source])


with open(PICKS_FILE, encoding="utf-8-sig") as f:
    for number, line in enumerate(f, start=1):
        line = line.split("#")[0].strip()          # text after # is a comment
        if not line:
            continue
        code, _, alias = line.partition("=")
        code, alias = code.strip(), alias.strip()
        if code.lower().startswith(("myfcd_", "tkpi_")):
            food = foods.get(code.lower())
            if food is None:
                problems.append(f"{PICKS_FILE} line {number}: {code!r} not found. "
                                "Run build_foods.py first, then food_search.py.")
                continue
            if food["macros_imputed"] == "yes":
                problems.append(f"{PICKS_FILE} line {number}: {code} {food['name']} has imputed "
                                "macros (a group average, not a measurement). Use a measured "
                                "food or put pack-label values in my_ingredients.csv.")
                continue
            add(alias or food["name"], food["kcal"], food["protein_g"], food["carbs_g"],
                food["fat_g"], f"{food['source']} {code} via food-nutrition", f"{PICKS_FILE} line {number}")
            continue
        code = code.upper()
        food = tkpi.get(code)
        if food is None:
            problems.append(f"{PICKS_FILE} line {number}: {code!r} is not a TKPI code")
            continue
        if food["check"] != "ok":
            print(f"WARNING: {code} {food['name']}: {food['check']}. "
                  "Compare it with the PDF before relying on it.")
        add(alias or food["name"], food["kcal"], food["protein_g"], food["carbs_g"],
            food["fat_g"], f"TKPI 2017 {code} ({food['source']})", f"{PICKS_FILE} line {number}")

if os.path.exists(OWN_FILE):
    with open(OWN_FILE, newline="", encoding="utf-8-sig") as f:
        for number, r in enumerate(csv.DictReader(f), start=2):
            try:
                add(r["name"].strip(), r["kcal"], r["protein_g"], r["carbs_g"], r["fat_g"],
                    (r.get("source") or "label").strip(), f"{OWN_FILE} line {number}")
            except KeyError as e:
                problems.append(f"{OWN_FILE}: missing column {e}")
                break

if problems:
    print("Nothing written. Fix these first:")
    for p in problems:
        print(" -", p)
    sys.exit(1)

with open(OUT_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(COLUMNS)
    writer.writerows(rows)
print(f"Wrote {len(rows)} ingredients to {OUT_FILE}")