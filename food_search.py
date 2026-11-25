import csv
import sys

# short names for --high  ->  column in foods.csv
NUTRIENTS = {
    "iron": "iron_mg", "besi": "iron_mg",
    "calcium": "calcium_mg", "kalsium": "calcium_mg",
    "zinc": "zinc_mg", "seng": "zinc_mg",
    "magnesium": "magnesium_mg",
    "fiber": "fiber_g", "serat": "fiber_g",
    "vitc": "vitamin_c_mg",
    "potassium": "potassium_mg", "kalium": "potassium_mg",
    "sodium": "sodium_mg", "natrium": "sodium_mg",
}

USAGE = """Usage:
  python food_search.py biskuit                 search by name (several words must all match)
  python food_search.py --high iron             foods richest in a nutrient
  python food_search.py --high iron ikan        ...only foods whose name contains 'ikan'
  python food_search.py --high calcium --all    ...also show values that were imputed
Nutrients for --high: """ + ", ".join(sorted(NUTRIENTS))

args = sys.argv[1:]
if not args:
    sys.exit(USAGE)

with open("foods.csv", newline="", encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))

high = None
include_imputed = "--all" in args
args = [a for a in args if a != "--all"]
if args and args[0] == "--high":
    if len(args) < 2 or args[1].lower() not in NUTRIENTS:
        sys.exit(USAGE)
    high = NUTRIENTS[args[1].lower()]
    args = args[2:]

words = [w.lower() for w in args]
hits = [r for r in rows if all(w in r["name"].lower() for w in words)]

if high:
    def usable(r):
        if r[high] == "":
            return False
        return include_imputed or high not in r["imputed_fields"].split(";")
    hits = sorted((r for r in hits if usable(r)), key=lambda r: float(r[high]), reverse=True)
    unit = high.rsplit("_", 1)[1]
    print(f"Per 100 g, highest {high[:-len(unit) - 1]} first"
          + ("" if include_imputed else " (measured values only; add --all to include imputed)") + "\n")
    for r in hits[:15]:
        est = "  ~ imputed" if high in r["imputed_fields"].split(";") else ""
        flag = "  [macros imputed]" if r["macros_imputed"] == "yes" else ""
        print(f"{r['food_id']:11} {r['name'][:38]:38} {float(r[high]):8.1f} {unit}  "
              f"{r['kcal']:>6} kcal{est}{flag}")
    print(f"\n{len(hits)} food(s), showing the first 15")
    print("Add one to picks.txt like:  tkpi_0395 = Buncis")
    sys.exit(0)

for r in hits[:40]:
    flag = "  <-- macros IMPUTED (group average), not measured" if r["macros_imputed"] == "yes" else ""
    print(f"{r['food_id']:11} {r['name'][:40]:40} {r['kcal']:>6} kcal  "
          f"P {r['protein_g']:>5}  C {r['carbs_g']:>5}  F {r['fat_g']:>5}{flag}")

print(f"\n{len(hits)} match(es)" + (", showing the first 40" if len(hits) > 40 else ""))
print("Add one to picks.txt like:  myfcd_0003 = Biskuit marie   (old TKPI codes like AP001 still work too)")