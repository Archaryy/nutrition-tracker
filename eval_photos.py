"""Measure how accurate photo scanning is on YOUR meals, so changes can be judged by numbers.

Setup: make a folder  eval/  with some meal photos and a file  eval/truth.csv  like this
(one line per food on the plate; grams from a kitchen scale if you can):

    file,name,grams
    lunch1.jpg,nasi putih,150
    lunch1.jpg,ayam goreng,90
    lunch1.jpg,sayur bayam,60

Run:   python eval_photos.py            (or:  OLLAMA_MODEL=qwen2.5vl:3b python eval_photos.py)
"""
import csv
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import photo_ai
from database import DB_FILE
from food_match import load_foods, suggest, user_foods
import weights

FOLDER = Path("eval")


def main():
    truth_file = FOLDER / "truth.csv"
    if not truth_file.exists():
        sys.exit("Put photos and eval/truth.csv in the eval folder first (see the top of this file).")
    truth = defaultdict(list)
    with open(truth_file, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            truth[r["file"]].append((r["name"], float(r["grams"])))

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    foods = user_foods(conn) + load_foods()

    def food_of(name, alt=None, kind=None):
        found = suggest(name, foods, 1, alt=alt, kind=kind)
        return found[0][1]["food_id"] if found else None

    hits = missed = extra = 0
    errors = []
    for filename, wanted in truth.items():
        try:
            seen = photo_ai.analyze((FOLDER / filename).read_bytes())
        except (photo_ai.PhotoAIError, OSError) as e:
            print(f"{filename}: skipped ({e})")
            continue
        got = {}
        for it in seen:
            fid = food_of(it["name"], it.get("name_en"), it.get("kind"))
            if fid and fid not in got:
                got[fid] = weights.estimate(it)[0]
        print(f"\n{filename}")
        for name, grams in wanted:
            fid = food_of(name)
            if fid in got:
                hits += 1
                err = abs(got[fid] - grams) / grams
                errors.append(err)
                print(f"  ok      {name:22} real {grams:5.0f} g, model {got[fid]:5.0f} g ({err:.0%} off)")
            else:
                missed += 1
                print(f"  MISSED  {name}")
        wanted_ids = {food_of(n) for n, _ in wanted}
        for it in seen:
            if food_of(it["name"], it.get("name_en"), it.get("kind")) not in wanted_ids:
                extra += 1
                print(f"  extra   {it['name']} ({it['grams']:.0f} g)")
    total = hits + missed
    if total:
        print(f"\nFound {hits} of {total} foods ({hits / total:.0%}); {extra} extra items.")
    if errors:
        errors.sort()
        print(f"Weight error on the foods found: typical {errors[len(errors) // 2]:.0%}, "
              f"mean {sum(errors) / len(errors):.0%}.")


if __name__ == "__main__":
    main()