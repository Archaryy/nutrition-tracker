from datetime import date, datetime, timedelta
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from database import get_connection, init_db
from food_match import load_foods, suggest, user_foods, CONFIDENT
import base64
import csv
import os
import photo_ai

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.get("/styles.css")
def styles():
    return FileResponse("templates/styles.css", media_type="text/css")

MEAL_TYPES = ["Sarapan", "Makan Siang", "Makan Malam", "Camilan"]

init_db()

with get_connection() as _conn:
    _conn.execute("""
                  CREATE TABLE IF NOT EXISTS targets (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            kcal REAL NOT NULL, protein REAL NOT NULL, carbs REAL NOT NULL, fat REAL NOT NULL)
                  """)
ACTIVITIES = [
    ("1.2", "Hampir tidak olahraga (kerja duduk)"),
    ("1.375", "Olahraga ringan 1-3x/minggu"),
    ("1.55", "Olahraga sedang 3-5x/minggu"),
    ("1.725", "Olahraga berat 6-7x/minggu"),
]

GOALS = [
    ("lose", "Turun berat badan"),
    ("maintain", "Jaga berat badan"),
    ("gain", "Naik berat/ otot")
]

def get_targets(conn):
    return conn.execute("SELECT kcal, protein, carbs, fat FROM targets WHERE id = 1").fetchone()

def suggest_targets(sex, age, weight, height, activity, goal):
    """Mifflin-St Jeor BMR x activity, then adjust for the goal."""
    bmr = 10 * weight + 6.25 * height - 5 * age + (5 if sex == "m" else -161)
    tdee = bmr * activity
    if goal == "lose":
        kcal = max(tdee - 500, bmr)  # never below BMR
    elif goal == "gain":
        kcal = tdee + 300
    else:
        kcal = tdee
    protein = weight * {"lose": 1.6, "gain": 1.8, "maintain": 1.2}[goal]
    fat = kcal * 0.25 / 9
    carbs = max((kcal - protein * 4 - fat * 9) / 4, 0)
    return {k: round(v) for k, v in
            {"tdee": tdee, "kcal": kcal, "protein": protein, "carbs": carbs, "fat": fat}.items()}

def default_meal_type(now):
    if now.hour < 10:
        return "Sarapan"
    if now.hour < 15:
        return "Makan Siang"
    if now.hour < 18:
        return "Camilan"
    if now.hour < 21:
        return "Makan Malam"
    return "Camilan"

def parse_day(text):
    """Turn '2026-11-123' into a date, or fall back to today."""
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError):
        return date.today()

ENTRIES_SQL = """
SELECT m.id, m.eaten_at, m.meal_type, m.servings,
       d.name, d.serving_label,
       m.servings * COALESCE(SUM(i.kcal_per_100g    * di.grams / 100.0), 0) AS kcal,
       m.servings * COALESCE(SUM(i.protein_per_100g * di.grams / 100.0), 0) AS protein,
       m.servings * COALESCE(SUM(i.carbs_per_100g   * di.grams / 100.0), 0) AS carbs,
       m.servings * COALESCE(SUM(i.fat_per_100g     * di.grams / 100.0), 0) AS fat
FROM meal_log m
JOIN dishes d ON d.id = m.dish_id
LEFT JOIN dish_ingredients di ON di.dish_id = d.id
LEFT JOIN ingredients i ON i.id = di.ingredient_id
WHERE date(m.eaten_at) = ?
GROUP BY m.id
ORDER BY m.eaten_at, m.id
"""

# nutrient key -> (label, unit, rough adult daily reference). The reference is only a
# general yardstick, not personal advice: needs differ by age, sex and condition.
MICROS = {
    "fiber_g": ("Serat", "g", 25),
    "calcium_mg": ("Kalsium", "mg", 1000),
    "iron_mg": ("Zat besi", "mg", 15),
    "zinc_mg": ("Seng", "mg", 10),
    "magnesium_mg": ("Magnesium", "mg", 350),
    "vitamin_c_mg": ("Vitamin C", "mg", 75),
    "sodium_mg": ("Natrium", "mg", 2000),
}

MICRO_SQL = """
SELECT im.nutrient,
       SUM(m.servings * im.per_100g * di.grams / 100.0) AS total,
       SUM(CASE WHEN im.imputed = 1 THEN m.servings * im.per_100g * di.grams / 100.0
                ELSE 0 END) AS imputed_total
FROM meal_log m
JOIN dish_ingredients di ON di.dish_id = m.dish_id
JOIN ingredient_micros im ON im.ingredient_id = di.ingredient_id
WHERE date(m.eaten_at) = ?
GROUP BY im.nutrient
"""


def load_akg(path="akg.csv"):
    """AKG 2019 (Permenkes 28/2019, Tabel 1-3), adults and teens, as a list of rows."""
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


AKG_ROWS = load_akg()


def akg_for(profile):
    """The AKG row for this person's sex and age, or None (then generic values are used)."""
    if profile is None:
        return None
    for r in AKG_ROWS:
        if r["sex"] == profile["sex"] and int(r["age_min"]) <= profile["age"] <= int(r["age_max"]):
            return r
    return None


def get_profile(conn):
    return conn.execute("SELECT sex, age FROM profile WHERE id = 1").fetchone()


def day_micros(conn, day, akg=None):
    found = {r["nutrient"]: r for r in conn.execute(MICRO_SQL, (day.isoformat(),))}
    out = []
    for key, (label, unit, ref) in MICROS.items():
        if akg is not None and akg.ge(key, "") != "":
            ref = float(akg[key])
        r = found.get(key)
        total = r["total"] if r else 0.0
        out.append({"label": label, "unit": unit, "ref": ref, "total": total,
                    "imputed_pct": (100 * r["imputed_total"] / total) if r and total else 0,
                    "limit": key == "sodium_mg"})
    return out

WEEK_MICRO_SQL = """
SELECT date(m.eaten_at) AS day, im.nutrient,
       SUM(m.servings * im.per_100g * di.grams / 100.0) AS total
FROM meal_log m
JOIN dish_ingredients di ON di.dish_id = m.dish_id
JOIN ingredient_micros im ON im.ingredient_id = di.ingredient_id
WHERE date(m.eaten_at) BETWEEN ? AND ?
GROUP BY day, im.nutrient
"""


def week_micros(conn, first, last, logged_days, akg=None):
    """Average per logged day, and on how many logged days the reference was reached."""
    if not logged_days:
        return []
    per_day = {}
    for r in conn.execute(WEEK_MICRO_SQL, (first.isoformat(), last.isoformat())):
        per_day[(r["day"], r["nutrient"])] = r["total"]
    out = []
    for key, (label, unit, ref) in MICROS.items():
        if akg is not None and akg.get(key, "") != "":
            ref = float(akg[key])
        totals = [per_day.get((d, key), 0.0) for d in logged_days]
        limit = key == "sodium_mg"
        hit = sum(1 for t in totals if (t <= ref if limit else t >= ref))
        out.append({"label": label, "unit": unit, "ref": ref, "limit": limit,
                    "avg": sum(totals) / len(totals), "hit": hit, "days": len(totals)})
    return out

@app.get("/")
def home(request: Request, day: str =""):
    shown = parse_day(day)
    now = datetime.now()
    with get_connection() as conn:
        entries = conn.execute(ENTRIES_SQL, (shown.isoformat(), )).fetchall()
        dishes = conn.execute(
            "SELECT id, name, serving_label FROM dishes ORDER BY name"
        ).fetchall()
        targets = get_targets(conn)
        akg = akg_for(get_profile(conn))
        micros = day_micros(conn, shown, akg) if entries else []
        totals = {
            key: sum(e[key] for e in entries) for key in ("kcal", "protein", "carbs", "fat")
        }
    return templates.TemplateResponse(request, "index.html", {
        "page": "today",
        "targets": targets,
        "day": shown,
        "prev_day": shown - timedelta(days=1),
        "next_day": shown + timedelta(days=1),
        "is_today": shown == date.today(),
        "entries": entries,
        "dishes": dishes,
        "totals": totals,
        "micros": micros,
        "akg": akg,
        "meal_types": MEAL_TYPES,
        "default_meal": default_meal_type(now),
        "now_time": now.strftime("%H:%M"),
    })
    
@app.post("/log")
def log_meal(
    day: str = Form(...),
    time: str = Form(...),
    meal_type: str = Form(...),
    dish_id: int = Form(...),
    servings: float = Form(...),
):
    try:
        eaten_at = datetime.fromisoformat(f"{day} {time}")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date or time")
    if meal_type not in MEAL_TYPES:
        raise HTTPException(status_code=400, detail="Invalid meal type")
    if not 0 < servings <= 20:
        raise HTTPException(status_code=400, detail="Servings must be above 0 and at most 20")

    with get_connection() as conn:
        exists = conn.execute("SELECT 1 FROM dishes WHERE id = ?", (dish_id,)).fetchone()
        if exists is None:
            raise HTTPException(status_code=400, detail="Unknown dish")
        conn.execute(
            "INSERT INTO meal_log (eaten_at, meal_type, dish_id, servings) VALUES (?, ?, ?, ?)",
            (eaten_at.strftime("%Y-%m-%d %H:%M"), meal_type, dish_id, servings),
        )
    return RedirectResponse(f"/?day={eaten_at.date().isoformat()}", status_code=303)


@app.post("/delete/{entry_id}")
def delete_entry(entry_id: int, day: str = Form("")):
    with get_connection() as conn:
        conn.execute("DELETE FROM meal_log WHERE id = ?", (entry_id,))
    return RedirectResponse(f"/?day={parse_day(day).isoformat()}", status_code=303)

DAILY_SQL = """
SELECT date(m.eaten_at) AS day,
       SUM(m.servings * COALESCE(i.kcal_per_100g    * di.grams / 100.0, 0)) AS kcal,
       SUM(m.servings * COALESCE(i.protein_per_100g * di.grams / 100.0, 0)) AS protein,
       SUM(m.servings * COALESCE(i.carbs_per_100g   * di.grams / 100.0, 0)) AS carbs,
       SUM(m.servings * COALESCE(i.fat_per_100g     * di.grams / 100.0, 0)) AS fat
FROM meal_log m
LEFT JOIN dish_ingredients di ON di.dish_id = m.dish_id
LEFT JOIN ingredients i ON i.id = di.ingredient_id
WHERE date(m.eaten_at) BETWEEN ? AND ?
GROUP BY date(m.eaten_at)
"""


@app.get("/week")
def week(request: Request, end: str = ""):
    last = parse_day(end)
    first = last - timedelta(days=6)
    with get_connection() as conn:
        rows = {r["day"]: r for r in conn.execute(DAILY_SQL, (first.isoformat(), last.isoformat()))}
        targets = get_targets(conn)
        akg = akg_for(get_profile(conn))
        micros = week_micros(conn, first, last, sorted(rows), akg)
    days = []
    for n in range(7):
        d = first + timedelta(days=n)
        r = rows.get(d.isoformat())
        days.append({"date": d, "logged": r is not None,
                     "kcal": r["kcal"] if r else 0.0})
    logged = [rows[k] for k in rows]
    avg = {key: (sum(r[key] for r in logged) / len(logged) if logged else 0)
           for key in ("kcal", "protein", "carbs", "fat")}
    scale = max([d["kcal"] for d in days] + [targets["kcal"] if targets else 0, 1]) * 1.1
    return templates.TemplateResponse(request, "week.html", {
        "page": "week", "days": days, "targets": targets, "avg": avg,
        "logged_days": len(logged), "scale": scale, "micros": micros, "akg": akg,
        "prev_end": last - timedelta(days=7), "next_end": last + timedelta(days=7),
    })


def _float(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


@app.get("/settings")
def settings(request: Request, saved: int = 0, sex: str = "", age: str = "", weight: str = "",
             height: str = "", activity: str = "1.375", goal: str = "maintain"):
    with get_connection() as conn:
        current = get_targets(conn)
        profile = get_profile(conn)
    form = dict(current) if current else {"kcal": "", "protein": "", "carbs": "", "fat": ""}
    suggestion = None
    a, w, h, act = _float(age), _float(weight), _float(height), _float(activity)
    if (sex in ("m", "f") and goal in dict(GOALS) and activity in dict(ACTIVITIES)
            and a and w and h and 15 <= a <= 90 and 30 <= w <= 250 and 120 <= h <= 230):
        suggestion = suggest_targets(sex, a, w, h, act, goal)
        form = suggestion
    return templates.TemplateResponse(request, "settings.html", {
        "page": "settings", "saved": bool(saved), "profile": profile,
        "akg": akg_for(profile), "form": form, "suggestion": suggestion,
        "activities": ACTIVITIES, "goals": GOALS,
        "calc": {"sex": sex or "m", "age": age, "weight": weight, "height": height,
                 "activity": activity, "goal": goal},
    })


@app.post("/settings")
def save_settings(kcal: float = Form(...), protein: float = Form(...),
                  carbs: float = Form(...), fat: float = Form(...)):
    if not (800 <= kcal <= 6000 and 10 <= protein <= 500 and 20 <= carbs <= 900 and 10 <= fat <= 300):
        raise HTTPException(status_code=400, detail="Target di luar rentang wajar")
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO targets (id, kcal, protein, carbs, fat) VALUES (1, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET kcal=excluded.kcal, protein=excluded.protein,
               carbs=excluded.carbs, fat=excluded.fat""",
            (kcal, protein, carbs, fat))
    return RedirectResponse("/settings?saved=1", status_code=303)

@app.post("/profile")
def save_profile(sex: str = Form(...), age: int = Form(...)):
    if sex not in ("m", "f") or not 13 <= age <= 120:
        raise HTTPException(status_code=400, detail="Profil tidak valid")
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO profile (id, sex, age) VALUES (1, ?, ?)
               ON CONFLICT(id) DO UPDATE SET sex=excluded.sex, age=excluded.age""",
            (sex, age))
    return RedirectResponse("/settings?saved=1", status_code=303)



_FOODS_CSV = load_foods()   # loaded once at startup


@app.get("/photo")
def photo_upload(request: Request):
    """Show the photo upload form."""
    return templates.TemplateResponse(request, "photo_upload.html", {
        "page": "photo",
        "model": os.environ.get("OLLAMA_MODEL", "qwen2.5vl:7b"),
    })


@app.post("/photo")
async def photo_analyze(request: Request, photo: UploadFile = File(...)):
    """Receive the uploaded image, run Ollama, show the review form."""
    image_bytes = await photo.read()
    photo_b64 = base64.b64encode(image_bytes).decode("ascii")
    photo_src = f"data:{photo.content_type or 'image/jpeg'};base64,{photo_b64}"

    error = None
    detected = []
    try:
        detected = photo_ai.analyze(image_bytes)
    except photo_ai.PhotoAIError as exc:
        error = str(exc)

    with get_connection() as conn:
        all_foods = user_foods(conn) + _FOODS_CSV
        options = [r["name"] for r in all_foods]

    rows = []
    # pad to at least 5 rows so the user can add items manually
    for i in range(max(len(detected), 5)):
        item = detected[i] if i < len(detected) else None
        seen = item["name"] if item else ""
        grams = int(item["grams"]) if item else ""
        matches = suggest(seen, all_foods) if seen else []
        best_score, best = matches[0] if matches else (0, None)
        pick = best["name"] if best and best_score >= CONFIDENT else ""
        guess = best["name"] if best and best_score < CONFIDENT else ""
        rows.append({"seen": seen, "grams": grams, "pick": pick, "guess": guess})

    now = datetime.now()
    return templates.TemplateResponse(request, "photo_review.html", {
        "page": "photo",
        "photo": photo_b64,
        "photo_src": photo_src,
        "error": error,
        "rows": rows,
        "options": options,
        "day": date.today().isoformat(),
        "now_time": now.strftime("%H:%M"),
        "default_meal": default_meal_type(now),
        "meal_types": MEAL_TYPES,
    })


@app.post("/photo/save")
async def photo_save(request: Request):
    """Save the reviewed items from the photo as individual meal-log entries."""
    form = await request.form()
    day = parse_day(form.get("day", ""))
    time_str = form.get("time", datetime.now().strftime("%H:%M"))
    meal_type = form.get("meal_type", MEAL_TYPES[0])

    try:
        eaten_at = datetime.strptime(f"{day.isoformat()} {time_str}", "%Y-%m-%d %H:%M")
    except ValueError:
        eaten_at = datetime.combine(day, datetime.now().time())

    with get_connection() as conn:
        all_foods = user_foods(conn) + _FOODS_CSV
        name_to_food = {r["name"]: r for r in all_foods}

        i = 0
        while True:
            food_name = (form.get(f"food_{i}") or "").strip()
            grams_raw = (form.get(f"grams_{i}") or "").strip()
            if food_name == "" and grams_raw == "" and i >= 5:
                break
            if not food_name or not grams_raw:
                i += 1
                continue

            try:
                grams = float(grams_raw)
            except ValueError:
                i += 1
                continue

            food = name_to_food.get(food_name)
            if food is None:
                i += 1
                continue

            food_id = food["food_id"]   # e.g. "ing_12" or "tkpi_0395"
            dish_name = food_name

            if food_id.startswith("ing_"):
                ing_id = int(food_id.split("_")[1])
            else:
                # CSV food — look up or create the ingredient row
                existing_ing = conn.execute(
                    "SELECT id FROM ingredients WHERE name = ?", (dish_name,)).fetchone()
                if existing_ing:
                    ing_id = existing_ing["id"]
                else:
                    cur = conn.execute(
                        """INSERT INTO ingredients
                           (name, kcal_per_100g, protein_per_100g, carbs_per_100g, fat_per_100g)
                           VALUES (?, ?, ?, ?, ?)""",
                        (dish_name,
                         float(food.get("kcal") or 0),
                         float(food.get("protein_g") or 0),
                         float(food.get("carbs_g") or 0),
                         float(food.get("fat_g") or 0)))
                    ing_id = cur.lastrowid

            # Look up or create a single-ingredient dish by name
            dish = conn.execute(
                "SELECT id FROM dishes WHERE name = ?", (dish_name,)).fetchone()
            if dish is None:
                cur = conn.execute(
                    "INSERT INTO dishes (name, serving_label) VALUES (?, '1 porsi')",
                    (dish_name,))
                dish_id = cur.lastrowid
                conn.execute(
                    "INSERT INTO dish_ingredients (dish_id, ingredient_id, grams) VALUES (?, ?, ?)",
                    (dish_id, ing_id, grams))
            else:
                dish_id = dish["id"]
                conn.execute(
                    "UPDATE dish_ingredients SET grams = ? WHERE dish_id = ? AND ingredient_id = ?",
                    (grams, dish_id, ing_id))

            # Log servings=1 (all portion info lives in dish_ingredients.grams)
            conn.execute(
                "INSERT INTO meal_log (eaten_at, meal_type, dish_id, servings) VALUES (?, ?, ?, ?)",
                (eaten_at.strftime("%Y-%m-%d %H:%M"), meal_type, dish_id, 1))
            i += 1

    return RedirectResponse(f"/?day={day.isoformat()}", status_code=303)
