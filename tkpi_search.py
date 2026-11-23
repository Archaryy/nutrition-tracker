import csv
import sys
if len(sys.argv) < 2:
    sys.exit("Usage: python tkpi_search.py nasi   (several words must all match: python tkpi_search.py ayam goreng)")
    
words = [w.lower() for w in sys.argv[1:]]
with open("tkpi.csv", newline="", encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))

hits = [r for r in rows if all (w in r["name"].lower() for w in words)]
for r in hits [:40]:
    flag = "" if r["check"] == "ok" else "  <-- CHECK IN THE PDF: " + r["check"]
    print(f"{r['code']}  {r['name'][:44]:44} {r['kcal']:>5} kcal  "
          f"P {r['protein_g']:>5}  C {r['carbs_g']:>5}  F {r['fat_g']:>5}{flag}")

print(f"\n{len(hits)} match(es)" + (", showing the first 40" if len(hits) > 40 else ""))