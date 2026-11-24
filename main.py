from datetime import date, datetime, timedelta
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from database import get_connection, init_db

app = FastAPI()
templates = Jinja2Templates(directory="templates")

MEAL_TYPES = ["Sarapan", "Makan Siang", "Makan malam", "Camilan"]

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
        "logged_days": len(logged), "scale": scale,
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
    form = dict(current) if current else {"kcal": "", "protein": "", "carbs": "", "fat": ""}
    suggestion = None
    a, w, h, act = _float(age), _float(weight), _float(height), _float(activity)
    if (sex in ("m", "f") and goal in dict(GOALS) and activity in dict(ACTIVITIES)
            and a and w and h and 15 <= a <= 90 and 30 <= w <= 250 and 120 <= h <= 230):
        suggestion = suggest_targets(sex, a, w, h, act, goal)
        form = suggestion
    return templates.TemplateResponse(request, "settings.html", {
        "page": "settings", "saved": bool(saved), "form": form, "suggestion": suggestion,
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