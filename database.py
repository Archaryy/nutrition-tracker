import sqlite3

DB_FILE = "foodtracker.db"


def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # lets us read columns by name
    conn.execute("PRAGMA foreign_keys = ON")  # enforce links between tables
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            kcal_per_100g REAL NOT NULL,
            protein_per_100g REAL NOT NULL,
            carbs_per_100g REAL NOT NULL,
            fat_per_100g REAL NOT NULL,
            source TEXT
        );

        CREATE TABLE IF NOT EXISTS ingredient_micros (
            ingredient_id INTEGER NOT NULL REFERENCES ingredients(id) ON DELETE CASCADE,
            nutrient TEXT NOT NULL,
            per_100g REAL NOT NULL,
            imputed INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (ingredient_id, nutrient)
        );

        CREATE TABLE IF NOT EXISTS dishes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            serving_label TEXT NOT NULL DEFAULT '1 porsi',
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS dish_ingredients (
            dish_id INTEGER NOT NULL REFERENCES dishes(id) ON DELETE CASCADE,
            ingredient_id INTEGER NOT NULL REFERENCES ingredients(id),
            grams REAL NOT NULL,
            PRIMARY KEY (dish_id, ingredient_id)
        );

        CREATE TABLE IF NOT EXISTS meal_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            eaten_at TEXT NOT NULL,
            meal_type TEXT,
            dish_id INTEGER NOT NULL REFERENCES dishes(id),
            servings REAL NOT NULL DEFAULT 1,
            note TEXT
        );
        """)

def dish_totals(conn):
    """Calories and macros for ONE serving of every dish."""
    return conn.execute("""
        SELECT d.name,
               d.serving_label,
               ROUND(SUM(i.kcal_per_100g    * di.grams / 100.0), 1) AS kcal,
               ROUND(SUM(i.protein_per_100g * di.grams / 100.0), 1) AS protein,
               ROUND(SUM(i.carbs_per_100g   * di.grams / 100.0), 1) AS carbs,
               ROUND(SUM(i.fat_per_100g     * di.grams / 100.0), 1) AS fat
        FROM dishes d
        JOIN dish_ingredients di ON di.dish_id = d.id
        JOIN ingredients i ON i.id = di.ingredient_id
        GROUP BY d.id
        ORDER BY d.name
    """).fetchall()

if __name__ == "__main__":
    init_db()
    print("Database ready:", DB_FILE)