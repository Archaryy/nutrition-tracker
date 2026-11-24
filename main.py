from datetime import date, datetime, timedelta
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from database import get_connection, init_db

app = FastAPI()
templates = Jinja2Templates(directory="templates")

MEAL_TYPES = ["Sarapan", "Makan Siang", "Makan malam", "Camilan"]

init_db()

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
        totals = {
            key: sum(e[key] for e in entries) for key in ("kcal", "protein", "carbs", "fat")
        }
    return templates.TemplateResponse(request, "index.html", {
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