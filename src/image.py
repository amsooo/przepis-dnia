import base64
import io
import sys
import time
import urllib.parse

import requests
from PIL import Image

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
    """Magnific API (kredyty z planu). Format odpowiedzi obsługiwany defensywnie: base64, URL lub zadanie asynchroniczne."""
    key = config.env("MAGNIFIC_API_KEY")
    url = "https://api.magnific.com/v1/ai/text-to-image"
    headers = {"x-magnific-api-key": key, "Content-Type": "application/json"}
    body = {"prompt": prompt, "num_images": 1}
    size = config.env("MAGNIFIC_IMAGE_SIZE", "", required=False)
    if size:
        body["image"] = {"size": size}
    resp = requests.post(url, headers=headers, json=body, timeout=180)
    resp.raise_for_status()
    data = resp.json()
    for _ in range(30):  # jeśli API zwróciło zadanie, czekamy na wynik
        found = _extract_image(data)
        if found:
            return found
        task = (data.get("data") or {}) if isinstance(data.get("data"), dict) else {}
        task_id = task.get("task_id")
        if not task_id:
            break
        time.sleep(4)
        poll = requests.get(f"{url}/{task_id}", headers=headers, timeout=60)
        poll.raise_for_status()
        data = poll.json()
    raise RuntimeError(f"Magnific: nieznany format odpowiedzi: {str(data)[:200]}")


def _extract_image(data):
    items = data.get("data")
    if isinstance(items, dict):
        items = items.get("generated") or []
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
    w, h = img.size
    target_h = int(w * 5 / 4)
    if h > target_h:
        top = (h - target_h) // 2
        img = img.crop((0, top, w, top + target_h))
    img.save(out_path, "JPEG", quality=88)
    return name, errors
