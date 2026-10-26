import time

import requests

from . import config


def _check(resp):
    """Podnosi błąd z komunikatem od Meta (nie zawiera tokenu) zamiast gołego 'Bad Request'."""
    if resp.ok:
        return resp
    try:
        err = resp.json().get("error", {})
        detail = err.get("error_user_msg") or err.get("message") or resp.text[:200]
    except ValueError:
        detail = resp.text[:200]
    raise RuntimeError(f"Instagram {resp.status_code}: {detail}")

def publish_photo(image_url, caption):
    GRAPH = config.ig_host()
    user_id = config.env("IG_USER_ID")
    token = config.env("IG_ACCESS_TOKEN")
    r = requests.post(f"{GRAPH}/{user_id}/media",
                      data={"image_url": image_url, "caption": caption, "access_token": token}, timeout=60)
    _check(r)
    creation_id = r.json()["id"]
    for _ in range(20):  # czekamy aż Meta przetworzy zdjęcie
        s = requests.get(f"{GRAPH}/{creation_id}",
                         params={"fields": "status_code", "access_token": token}, timeout=30).json()
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram odrzucił zdjęcie: {s}")
        time.sleep(3)
    r = requests.post(f"{GRAPH}/{user_id}/media_publish",
                      data={"creation_id": creation_id, "access_token": token}, timeout=60)
    _check(r)
    return r.json()["id"]
