import csv
import sys

if len(sys.argv) < 2:
    sys.exit("Usage: python food_search.py biskuit   (several words must all match: python food_search.py ayam goreng)")

words = [w.lower() for w in sys.argv[1:]]
with open("foods.csv", newline="", encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))

hits = [r for r in rows if all(w in r["name"].lower() for w in words)]
for r in hits[:40]:
    flag = "  <-- macros IMPUTED (group average), not measured" if r["macros_imputed"] == "yes" else ""
    print(f"{r['food_id']:11} {r['name'][:40]:40} {r['kcal']:>6} kcal  "
          f"P {r['protein_g']:>5}  C {r['carbs_g']:>5}  F {r['fat_g']:>5}{flag}")

print(f"\n{len(hits)} match(es)" + (", showing the first 40" if len(hits) > 40 else ""))
print("Add one to picks.txt like:  myfcd_0003 = Biskuit marie   (old TKPI codes like AP001 still work too)")
