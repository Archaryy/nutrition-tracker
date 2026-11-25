"""Ask a local vision model (Ollama) what is on a meal photo.

Setup (once):  install Ollama from ollama.com, then   ollama pull qwen2.5vl:7b
Change the model with the OLLAMA_MODEL environment variable if your computer is small
(for example OLLAMA_MODEL=qwen2.5vl:3b) or large. Nothing leaves your computer.
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

PROMPT = (
    "You are a nutrition assistant. Look at this photo of a meal and list every separate "
    "food or ingredient you can see. For each one give a short name in Indonesian (for "
    "example 'nasi putih', 'ayam goreng', 'tempe goreng', 'sayur bayam') and your best "
    "estimate of its cooked weight in grams. Do not invent items you cannot see. "
    'Reply with JSON only, in exactly this shape: {"items": [{"name": "nasi putih", "grams": 150}]}'
)


class PhotoAIError(Exception):
    """The model could not be reached or gave an unusable answer."""


def parse_items(text):
    """Turn the model's reply into [{'name': str, 'grams': float}], tolerating junk around it."""
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
        items.append({"name": name[:80], "grams": min(max(grams, 1.0), 2000.0)})
    return items[:15]


def analyze(image_bytes):
    """Send the photo to Ollama and return the detected items."""
    payload = {
        "model": MODEL,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
        "messages": [{"role": "user", "content": PROMPT,
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