"""Ask a local vision model (Ollama) what is on a meal photo.
"""
import base64
import json
import os
import re
import urllib.error
import urllib.request

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5vl:7b")
TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "300"))

PROMPT = """You are a nutrition assistant for an Indonesian user. Look at this photo of a meal.
List every separate food you can see.

Rules:
- One entry per distinct food: the rice, each side dish, each vegetable, a sauce if it is clearly a separate portion. A single mixed dish (nasi goreng, soto, gado-gado) is ONE entry.
- "name": a short Indonesian name that says how it was cooked, for example "ayam goreng" (not just "ayam"), "tempe goreng", "tahu bacem", "sayur bayam", "nasi putih", "telur dadar".
- "name_en": the same food in plain English, for example "fried chicken".
- "grams": your best estimate of the weight of that food on the plate, as eaten. Use size clues: a standard dinner plate is about 25 cm across; a level rice scoop is about 100 g and a heaped serving about 150-200 g; a palm-sized piece of cooked meat or fish is about 90 g; one egg is about 50 g.
- Only list what you can see. Do not invent hidden ingredients and do not repeat a food.
{hints}
Reply with JSON only, exactly in this shape:
{{"items": [{{"name": "nasi putih", "name_en": "steamed white rice", "grams": 150}}]}}"""


def build_prompt(usual=()):
    """The prompt, with the foods this person often eats as naming hints."""
    hints = ""
    if usual:
        hints = ("Foods this person often eats (use these exact names when the photo shows the "
                 "same food): " + ", ".join(usual[:20]) + "\n")
    return PROMPT.format(hints=hints)


class PhotoAIError(Exception):
    """The model could not be reached or gave an unusable answer."""


def parse_items(text):
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
        try:
            grams = float(str(entry.get("grams")).lower().replace("g", "").replace(",", ".").strip())
        except ValueError:
            grams = 100.0
        if not name:
            continue
        name_en = str(entry.get("name_en") or "").strip()[:80]
        items.append({"name": name[:80], "name_en": name_en,
                      "grams": min(max(grams, 1.0), 2000.0)})
    seen, unique = set(), []
    for it in items:
        k = it["name"].lower()
        if k not in seen:
            seen.add(k)
            unique.append(it)
    return unique[:15]


def analyze(image_bytes, usual=()):
    """Send the photo to Ollama and return the detected items. `usual` = foods you often eat."""
    payload = {
        "model": MODEL,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
        "messages": [{"role": "user", "content": build_prompt(usual),
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