"""Estimate how many grams a food on the photo weighs.

A photo cannot be put on a scale, so this is a rule of thumb, but an open one:
  1. If the model could COUNT the food (3 pieces of fried tempeh, 2 eggs), grams = count x a
     typical weight of one piece.
  2. Otherwise, if it could say how much of the PLATE the food covers (about half), grams =
     that share x what a completely covered plate holds, scaled to the size of your plate.
  3. Otherwise we keep the model's own guess.
The numbers below are typical household values, not measurements of YOUR food. Weigh a few
meals on a kitchen scale, compare, and edit the numbers. The app also learns your usual
weights from the corrections you save.
"""

# What one counted item typically weighs, in grams: (kind, unit) first, then (None, unit)
UNIT_GRAMS = {
    ("chicken", "piece"): 75, ("chicken", "slice"): 30,
    ("beef", "piece"): 50, ("beef", "slice"): 20,
    ("pork", "piece"): 50, ("pork", "slice"): 20,
    ("fish", "piece"): 80, ("seafood", "piece"): 15,
    ("egg", "egg"): 55, ("egg", "piece"): 55,
    ("tofu_tempeh", "piece"): 35,
    ("bread", "slice"): 30, ("bread", "piece"): 50,
    ("snack", "piece"): 25, ("fruit", "piece"): 100,
    ("rice", "spoon"): 100, ("rice", "bowl"): 160,
    ("noodle", "bowl"): 300,
    ("soup", "bowl"): 300, ("soup", "cup"): 200,
    ("drink", "cup"): 240,
    ("sauce", "spoon"): 15,
    (None, "bowl"): 200, (None, "cup"): 200, (None, "spoon"): 20,
    (None, "piece"): 60, (None, "slice"): 25, (None, "egg"): 55,
}
# What a plate holds when the food covers all of a 24 cm plate (cooked, as eaten)
FULL_PLATE_GRAMS = {
    "rice": 480, "noodle": 400, "bread": 250, "vegetable": 280, "chicken": 500, "beef": 500,
    "pork": 500, "fish": 450, "seafood": 400, "egg": 450, "tofu_tempeh": 450, "fruit": 400,
    "snack": 250, "other": 400,
}
UNIT_NAMES = {"piece": "potong", "slice": "iris", "egg": "butir", "bowl": "mangkuk",
              "cup": "gelas", "spoon": "sendok"}
REFERENCE_PLATE_CM = 24


def _number(value, low, high):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if low < v <= high else None


def estimate(item, plate_cm=REFERENCE_PLATE_CM):
    """(grams, how) for one detected item. `how` is a short Indonesian note saying where the
    number came from, shown under the weight so you can judge it."""
    kind, unit = item.get("kind"), item.get("unit")
    count = _number(item.get("count"), 0, 40)
    if count and unit in UNIT_NAMES:
        per = UNIT_GRAMS.get((kind, unit)) or UNIT_GRAMS.get((None, unit))
        if per:
            return round(count * per), f"{count:g} {UNIT_NAMES[unit]} × {per} g"
    share = _number(item.get("plate_share"), 0, 1)
    full = FULL_PLATE_GRAMS.get(kind) if kind in FULL_PLATE_GRAMS else None
    if share and full:
        grams = share * full * (plate_cm / REFERENCE_PLATE_CM) ** 2
        return round(grams), f"{round(share * 100)}% dari piring {plate_cm} cm"
    return round(min(max(float(item.get("grams") or 100), 5), 1500)), "tebakan model"