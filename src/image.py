import base64
import io
import urllib.parse

import requests
from PIL import Image

from . import config


def _gemini(prompt):
    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{config.image_model()}:generateContent",
        headers={"x-goog-api-key": config.env("GEMINI_API_KEY")},
        json={"contents": [{"parts": [{"text": prompt}]}],
              "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "4:5"}}},
        timeout=180,
    )
    resp.raise_for_status()
    for part in resp.json()["candidates"][0]["content"]["parts"]:
        inline = part.get("inlineData") or part.get("inline_data")
        if inline:
            return base64.b64decode(inline["data"])
    raise RuntimeError("Gemini nie zwrócił obrazu")


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


PROVIDERS = {"gemini": _gemini, "pollinations": _pollinations, "openai": _openai}


def generate(prompt, out_path):
    """Próbuje kolejnych dostawców, zapisuje JPEG 4:5 (wymóg proporcji IG)."""
    errors = []
    for name in config.image_providers():
        try:
            raw = PROVIDERS[name.strip()](prompt)
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            break
        except Exception as exc:  # 429, brak klucza, zły obraz: próbujemy następnego
            errors.append(f"{name}: {exc}")
    else:
        raise RuntimeError("Żaden dostawca obrazów nie zadziałał: " + " | ".join(errors))
    w, h = img.size
    target_h = int(w * 5 / 4)
    if h > target_h:
        top = (h - target_h) // 2
        img = img.crop((0, top, w, top + target_h))
    img.save(out_path, "JPEG", quality=88)
