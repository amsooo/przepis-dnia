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
    """Modele do wypróbowania po kolei, od najlepszego.

    kind="text"  -> rodzina flash (bez image/live/tts); warianty "lite" idą na koniec jako ostatnia deska ratunku,
    kind="image" -> modele generujące obrazy (bez lite).
    Kolejność: nie-lite przed lite, stabilne (bez preview/exp) przed testowymi, potem najwyższa wersja.
    """
    candidates = []
    for m in models:
        name = m["name"].removeprefix("models/")
        if "generateContent" not in m.get("supportedGenerationMethods", []):
            continue
        if not name.startswith("gemini-") or any(x in name for x in ("live", "tts", "audio", "embedding", "robotics", "computer-use")):
            continue
        is_image = "image" in name
        if kind == "image" and not is_image:
            continue
        if kind == "text" and (is_image or "flash" not in name):
            continue
        is_lite = "lite" in name
        if kind == "image" and is_lite:
            continue
        stable = not any(x in name for x in ("preview", "exp"))
        candidates.append((not is_lite, stable, _version_key(name), name))
    return [c[-1] for c in sorted(candidates, reverse=True)]


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


def model_chain(kind, override_var, fallback, limit=None):
    """Lista modeli do wypróbowania po kolei: jawnie ustawiony albo najlepsze z autodetekcji."""
    explicit = config.env(override_var, "", required=False)
    if explicit:
        return [explicit]
    limit = limit or (8 if kind == "text" else 3)   # przy przeciążeniu najnowszych modeli sięgamy do starszych
    try:
        return ranked(list_models(), kind)[:limit] or [fallback]
    except requests.RequestException:
        return [fallback]


def generate(kind, override_var, fallback, body, retries=2, timeout=90):
    """POST generateContent z ponawianiem i przełączaniem na kolejny model.

    5xx i błędy połączenia: ponawiamy z odstępem. Timeout (model się zawiesił) oraz 4xx
    (np. 429 limit, 404): od razu następny model, bo ponawianie tego samego nic nie da.
    """
    last = None
    for model in model_chain(kind, override_var, fallback):
        for attempt in range(retries):
            try:
                resp = requests.post(f"{BASE}/models/{model}:generateContent",
                                     headers={"x-goog-api-key": config.env("GEMINI_API_KEY")},
                                     json=body, timeout=timeout)
            except requests.Timeout:
                last = f"{model}: brak odpowiedzi w {timeout} s"
                print(f"[gemini] {last}", file=sys.stderr)
                break
            except requests.ConnectionError as exc:
                last = f"{model}: błąd połączenia ({type(exc).__name__})"
                print(f"[gemini] {last}", file=sys.stderr)
                time.sleep(10 * (attempt + 1))
                continue
            if resp.ok:
                return resp.json()
            last = f"{model}: HTTP {resp.status_code}"
            print(f"[gemini] {last}", file=sys.stderr)
            if resp.status_code < 500:
                break
            time.sleep((8, 20)[min(attempt, 1)])  # krótko: przy przeciążeniu lepiej szybko przejść do innego modelu
    raise RuntimeError(f"Gemini nie odpowiedział poprawnie ({last})")
