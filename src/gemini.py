import functools
import re
import sys
import time

import requests

from . import config

BASE = "https://generativelanguage.googleapis.com/v1beta"


def _version_key(name):
    m = re.search(r"gemini-(\d+(?:\.\d+)*)", name)
    return tuple(int(n) for n in m.group(1).split(".")) if m else (0,)


def ranked(models, kind):
    """Wybiera najlepszy model z listy zwróconej przez API.

    kind="text"  -> rodzina flash (bez lite/image/live/tts), "image" -> modele generujące obrazy.
    Preferuje wersje stabilne (bez preview/exp), potem najwyższy numer wersji.
    """
    candidates = []
    for m in models:
        name = m["name"].removeprefix("models/")
        if "generateContent" not in m.get("supportedGenerationMethods", []):
            continue
        if not name.startswith("gemini-") or any(x in name for x in ("lite", "live", "tts", "audio", "embedding", "robotics", "computer-use")):
            continue
        is_image = "image" in name
        if kind == "image" and not is_image:
            continue
        if kind == "text" and (is_image or "flash" not in name):
            continue
        stable = not any(x in name for x in ("preview", "exp"))
        candidates.append((stable, _version_key(name), name))
    return [name for _, _, name in sorted(candidates, reverse=True)]


def pick(models, kind):
    best = ranked(models, kind)
    return best[0] if best else None


@functools.lru_cache(maxsize=None)
def list_models():
    resp = requests.get(f"{BASE}/models", params={"pageSize": 200},
                        headers={"x-goog-api-key": config.env("GEMINI_API_KEY")}, timeout=60)
    resp.raise_for_status()
    return tuple({"name": m["name"], "supportedGenerationMethods": tuple(m.get("supportedGenerationMethods", []))}
                 for m in resp.json().get("models", []))


def model_for(kind, override_var, fallback):
    """Jawne ustawienie (zmienna środowiskowa) wygrywa; inaczej autodetekcja; inaczej wartość domyślna."""
    explicit = config.env(override_var, "", required=False)
    if explicit:
        return explicit
    try:
        return pick(list_models(), kind) or fallback
    except requests.RequestException:
        return fallback


def model_chain(kind, override_var, fallback, limit=3):
    """Lista modeli do wypróbowania po kolei: jawnie ustawiony albo najlepsze z autodetekcji."""
    explicit = config.env(override_var, "", required=False)
    if explicit:
        return [explicit]
    try:
        return ranked(list_models(), kind)[:limit] or [fallback]
    except requests.RequestException:
        return [fallback]


def generate(kind, override_var, fallback, body, retries=3, timeout=180):
    """POST generateContent z ponawianiem przy 5xx (z odstępem) i przełączaniem na kolejny model.

    Błąd 4xx (np. 429 limit, 404) nie jest ponawiany: przechodzimy od razu do następnego modelu.
    """
    last = None
    for model in model_chain(kind, override_var, fallback):
        for attempt in range(retries):
            resp = requests.post(f"{BASE}/models/{model}:generateContent",
                                 headers={"x-goog-api-key": config.env("GEMINI_API_KEY")},
                                 json=body, timeout=timeout)
            if resp.ok:
                return resp.json()
            last = f"{model}: HTTP {resp.status_code}"
            print(f"[gemini] {last}", file=sys.stderr)
            if resp.status_code < 500:
                break
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Gemini nie odpowiedział poprawnie ({last})")
