# Nutrition Tracker

Take a photo of a meal and the app lists what is on the plate, estimates the portions, and logs calories and nutrients. The interface is in Indonesian. Foods come from Indonesian food-composition data (TKPI and MyFCD), and daily targets use AKG 2019.

Runs on your own computer. By default nothing leaves it.

## What it does

- **Photo scan:** a vision model names each food, then the app matches it to a food in the database.
- **Review before saving:** every item can be changed. Type to search the food list, tap an alternative, edit grams.
- **Portion estimate:** from piece counts, how much of the plate a food covers, or the model's own guess. Shows which one was used.
- **Learns from you:** if you correct a food, the app suggests your choice next time.
- **Manual entry**, a **weekly view** with charts, and a **settings** page for your profile and targets.
- Works on phone and desktop layouts.

## Quick start

You need Python 3.10+ and [Ollama](https://ollama.com).

```
pip install -r requirements.txt
ollama pull qwen3-vl:8b-instruct
uvicorn main:app --reload
```

Open http://127.0.0.1:8000

Use the `-instruct` model tag. The plain tag is a "thinking" model and is slow.

The first photo after starting Ollama is slow because the model loads into memory. If it returns nothing, wait a minute and try again.

## Settings (environment variables)

Set these in the same terminal before `uvicorn`.

| Variable | Default | Use |
|---|---|---|
| `OLLAMA_MODEL` | `qwen3-vl:8b-instruct` | Local model name. Must match `ollama list`. |
| `OLLAMA_URL` | `http://localhost:11434` | Where Ollama runs. |
| `OLLAMA_TIMEOUT` | `300` | Seconds to wait for the model. |
| `PHOTO_BACKEND` | `ollama` | Set to `gemini` for the optional Google backend. |
| `GEMINI_API_KEY` | none | Key from aistudio.google.com. |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Check the current name in AI Studio. |

**Privacy:** with the default setup, photos stay on your computer. With `PHOTO_BACKEND=gemini` photos are sent to Google, and on the free tier Google may use them to improve its products. Never commit your API key.

PowerShell example: `$env:OLLAMA_MODEL="qwen3-vl:4b-instruct"`
Mac/Linux example: `export OLLAMA_MODEL=qwen3-vl:4b-instruct`

## Measure accuracy on your own meals

1. Make a folder `eval/` with 15 to 20 photos of meals you eat.
2. Add `eval/truth.csv`, one row per food on the plate (grams from a kitchen scale if you can):

   ```
   file,name,grams
   lunch1.jpg,nasi putih,150
   lunch1.jpg,ayam goreng,90
   ```
3. Run `python eval_photos.py`. It prints how many foods were found, extras, and typical weight error.
4. To compare models, run it again with `OLLAMA_MODEL=...` or `PHOTO_BACKEND=gemini`, then compare the last line.

To see exactly what the model answers for one photo: `python debug_photo.py path/to/photo.jpg`.

## Project layout

| File | Role |
|---|---|
| `main.py` | Web routes (FastAPI) |
| `photo_ai.py` | Prompt, model backends (Ollama, Gemini), reply parsing |
| `food_match.py` | Matches model names to foods; type-to-search |
| `weights.py` | Portion estimates (typical household values) |
| `photo_memory.py`, `photo_log.py` | Remembers your corrections |
| `database.py`, `foodtracker.db` | SQLite storage |
| `foods.csv`, `tkpi.csv`, `akg.csv` | Food data and daily targets |
| `build_foods.py`, `import_*.py`, `make_ingredients.py` | Data preparation scripts |
| `eval_photos.py`, `debug_photo.py`, `check_db.py`, `seed_test.py` | Testing tools |
| `templates/` | Pages, styles, icons |

## Known limits

- Recognition depends on the model. Published food benchmarks put cloud models ahead of small local ones, and none were found for Indonesian food specifically, so test on your own meals.
- Portion tables are typical household values. Check them against a kitchen scale and adjust `weights.py`.
- Phone browsers, dark mode and the plate-size setting have only been checked in a headless browser, not on real devices.
- Gemini free-tier limits and the current model name were not confirmed. Check AI Studio.

## Data sources

- TKPI (Indonesian Food Composition Table, Ministry of Health) and MyFCD
- AKG 2019 (Indonesian recommended nutrient intakes)
- Extra food data merged from the `food-nutrition` repository by intanypurbasari; imputed rows are excluded
