"""Ask a local vision model (Ollama) what is on a meal photo.

Setup (once):  install Ollama from ollama.com, then   ollama pull qwen3-vl:8b-instruct
Change the model with the OLLAMA_MODEL environment variable if your computer is small
(for example OLLAMA_MODEL=qwen3-vl:4b-instruct) or large. Nothing leaves your computer.
"""
import base64
import json
import os
import re
import urllib.error
import urllib.request

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_MODEL", "qwen3-vl:8b-instruct")
TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "300"))

KINDS = ("rice", "noodle", "bread", "chicken", "beef", "pork", "fish", "seafood", "egg",
         "tofu_tempeh", "vegetable", "fruit", "soup", "snack", "drink", "sauce", "other")
UNITS = ("piece", "slice", "egg", "bowl", "cup", "spoon", "none")

PROMPT = """You are a nutrition assistant for an Indonesian user. Look carefully at this photo of a meal and list every separate food on it.

For each food, write these fields in this order (describe first, then name):
- "look": 5 to 12 words on what you literally see: shape, colour, texture. Examples: "long thin yellow strands with sauce", "many small white separate grains", "golden crispy battered pieces".
- "kind": exactly one of: rice, noodle, bread, chicken, beef, pork, fish, seafood, egg, tofu_tempeh, vegetable, fruit, soup, snack, drink, sauce, other.
- "name": short Indonesian name that includes how it was cooked, for example "mie goreng", "dada ayam panggang", "tempe goreng", "nasi putih", "sayur bayam". Never just "daging": say which animal.
- "name_en": the same food in plain English.
- "count" and "unit": how many you can count, and of what. unit is one of: piece, slice, egg, bowl, cup, spoon, none. Use piece, slice or egg when you can count them, bowl or cup for soups and drinks, none for food heaped on a plate.
- "plate_share": for food on a plate, the fraction from 0 to 1 of the plate's surface it covers. Use 0 if it is not on a plate or you counted it.
- "grams": your best guess of its weight as eaten.

Rules:
- Noodles are long thin strands (mie, bihun, kwetiau, spaghetti). Rice is many small separate grains. Never call noodles rice.
- Kerupuk and keremes are pale, puffy, brittle fried snacks. They are not noodles.
- Sliced cooked chicken breast is "dada ayam".
- A single mixed dish (nasi goreng, mie ayam, soto, gado-gado) is ONE entry.
- Only list what you can see. Do not repeat a food.

Reply with JSON only, in exactly this shape:
{"items": [{"look": "long thin yellow strands with sauce", "kind": "noodle", "name": "mie goreng", "name_en": "fried noodles", "count": 1, "unit": "none", "plate_share": 0.5, "grams": 220}]}"""


def build_prompt():
    return PROMPT


class PhotoAIError(Exception):
    """The model could not be reached or gave an unusable answer."""


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_items(text):
    """Turn the model's reply into a list with one dict per food, tolerating junk around it."""
    if not text:
        raise PhotoAIError("The model returned an empty answer.")
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise PhotoAIError("The model's answer had no JSON in it.")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        raise PhotoAIError("The model's answer was not valid JSON.")
    raw = data.get("items") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        raise PhotoAIError("The model's answer had no 'items' list.")
    items = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        try:
            grams = float(str(entry.get("grams")).lower().replace("g", "").replace(",", ".").strip())
        except ValueError:
            grams = 100.0
        kind = str(entry.get("kind") or "").strip().lower().replace(" ", "_")
        unit = str(entry.get("unit") or "").strip().lower()
        items.append({
            "name": name[:80],
            "name_en": str(entry.get("name_en") or "").strip()[:80],
            "look": str(entry.get("look") or "").strip()[:120],
            "kind": kind if kind in KINDS else "other",
            "unit": unit if unit in UNITS else "none",
            "count": _num(entry.get("count")),
            "plate_share": _num(entry.get("plate_share")),
            "grams": min(max(grams, 1.0), 2000.0),
        })
    seen, unique = set(), []
    for it in items:                       # models sometimes list the same food twice
        k = it["name"].lower()
        if k not in seen:
            seen.add(k)
            unique.append(it)
    return unique[:15]


def analyze(image_bytes):
    """Send the photo to Ollama and return the detected items."""
    payload = {
        "model": MODEL,
        "stream": False,
        "format": "json",
        "think": False,                 # answer directly (some models "think" first and are slow)
        "options": {"temperature": 0},
        "messages": [{"role": "user", "content": build_prompt(),
                      "images": [base64.b64encode(image_bytes).decode("ascii")]}],
    }
    request = urllib.request.Request(
        OLLAMA_URL.rstrip("/") + "/api/chat", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            reply = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise PhotoAIError(f"Ollama does not have the model '{MODEL}'. Run: ollama pull {MODEL}")
        raise PhotoAIError(f"Ollama returned an error ({e.code}).")
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        raise PhotoAIError("Cannot reach Ollama. Is it running? Start it, then try again.")
    return parse_items((reply.get("message") or {}).get("content", ""))