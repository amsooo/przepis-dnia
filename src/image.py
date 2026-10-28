import base64
import io
import sys
import time
import urllib.parse

import requests
from PIL import Image, ImageEnhance

from . import config, gemini


def _gemini(prompt):
    data = gemini.generate("image", "IMAGE_MODEL", "gemini-2.5-flash-image", {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "4:5"}},
    }, timeout=150)
    for part in data["candidates"][0]["content"]["parts"]:
        inline = part.get("inlineData") or part.get("inline_data")
        if inline:
            return base64.b64decode(inline["data"])
    raise RuntimeError("Gemini nie zwrócił obrazu")


def _magnific(prompt):
    """Magnific API (kredyty z planu). Model z MAGNIFIC_MODEL (domyślnie seedream-v5-pro), zadania asynchroniczne.

    MAGNIFIC_MODEL=classic wywołuje starszy endpoint /v1/ai/text-to-image.
    """
    key = config.env("MAGNIFIC_API_KEY")
    model = config.env("MAGNIFIC_MODEL", "seedream-v5-pro", required=False)
    base = "https://api.magnific.com/v1/ai/text-to-image"
    url = base if model == "classic" else f"{base}/{model}"
    headers = {"x-magnific-api-key": key, "Content-Type": "application/json"}
    body = {"prompt": prompt}
    if model == "classic":
        body["num_images"] = 1
        body["negative_prompt"] = "fork, spoon, knife, cutlery, extra plates, side dishes, hands, text, watermark, deformed"
    aspect = config.env("MAGNIFIC_ASPECT_RATIO", "traditional_3_4", required=False)
    if aspect:
        body["aspect_ratio"] = aspect
    resp = requests.post(url, headers=headers, json=body, timeout=120)
    if resp.status_code == 400 and "aspect_ratio" in body:  # nieznana nazwa proporcji: bierzemy domyślną
        print(f"[magnific] 400 przy aspect_ratio={aspect}: {resp.text[:200]}", file=sys.stderr)
        body.pop("aspect_ratio")
        resp = requests.post(url, headers=headers, json=body, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    for _ in range(45):  # zadanie asynchroniczne: czekamy na wynik (do ok. 3 min)
        found = _extract_image(data)
        if found:
            return found
        task = _task(data)
        if str(task.get("status", "")).upper() in ("FAILED", "ERROR"):
            raise RuntimeError(f"Magnific: zadanie nieudane: {str(data)[:200]}")
        task_id = task.get("task_id")
        if not task_id:
            break
        time.sleep(4)
        poll = requests.get(f"{url}/{task_id}", headers=headers, timeout=60)
        poll.raise_for_status()
        data = poll.json()
    raise RuntimeError(f"Magnific: brak wyniku lub nieznany format odpowiedzi: {str(data)[:200]}")


def _task(data):
    """Dokumentacja bywa niespójna: pola zadania są w data albo na wierzchu."""
    inner = data.get("data")
    return inner if isinstance(inner, dict) else data


def _extract_image(data):
    items = _task(data).get("generated") if isinstance(_task(data), dict) else None
    if items is None and isinstance(data.get("data"), list):
        items = data["data"]
    for item in items or []:
        if isinstance(item, dict) and item.get("base64"):
            return base64.b64decode(item["base64"])
        link = item.get("url") if isinstance(item, dict) else item
        if isinstance(link, str) and link.startswith("http"):
            r = requests.get(link, timeout=120)
            r.raise_for_status()
            return r.content
    return None


def _pollinations(prompt):
    url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt) + "?width=1024&height=1280&nologo=true"
    resp = requests.get(url, timeout=180)
    resp.raise_for_status()
    return resp.content


def _openai(prompt):
    resp = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {config.env('OPENAI_API_KEY')}"},
        json={"model": "gpt-image-1", "prompt": prompt, "size": "1024x1536", "n": 1},
        timeout=180,
    )
    resp.raise_for_status()
    return base64.b64decode(resp.json()["data"][0]["b64_json"])


PROVIDERS = {"magnific": _magnific, "gemini": _gemini, "pollinations": _pollinations, "openai": _openai}


COLOR_BOOST, CONTRAST_BOOST = 1.25, 1.08
REQUIRED_KEYS = {"magnific": "MAGNIFIC_API_KEY", "gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY"}


def generate(prompt, out_path):
    """Próbuje kolejnych dostawców, zapisuje JPEG 4:5 (wymóg proporcji IG). Zwraca (dostawca, błędy poprzednich)."""
    errors = []
    for name in config.image_providers():
        name = name.strip()
        if name in REQUIRED_KEYS and not config.env(REQUIRED_KEYS[name], "", required=False):
            continue  # dostawca bez klucza to nie błąd, tylko nieskonfigurowany
        try:
            raw = PROVIDERS[name](prompt)
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            break
        except Exception as exc:  # 429, brak klucza, zły obraz: próbujemy następnego
            errors.append(f"{name}: {exc}")
            print(f"[obraz] {name} nie zadziałał: {exc}", file=sys.stderr)
    else:
        raise RuntimeError("Żaden dostawca obrazów nie zadziałał: " + " | ".join(errors))
    img = ImageEnhance.Color(img).enhance(COLOR_BOOST)       # żywsze kolory, żeby zdjęcie przyciągało wzrok
    img = ImageEnhance.Contrast(img).enhance(CONTRAST_BOOST)
    w, h = img.size
    target_h = int(w * 5 / 4)
    if h > target_h:
        top = (h - target_h) // 2
        img = img.crop((0, top, w, top + target_h))
    img.save(out_path, "JPEG", quality=88)
    return name, errors
