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
        if err.get("code") == 190:
            detail += " (token wygasł lub jest nieprawidłowy: wygeneruj nowy w panelu aplikacji Meta i podmień IG_ACCESS_TOKEN)"
    except ValueError:
        detail = resp.text[:200]
    raise RuntimeError(f"Instagram {resp.status_code}: {detail}")

def _wait_ready(graph, container_id, token):
    for _ in range(30):  # czekamy aż Meta przetworzy zdjęcie
        st = requests.get(f"{graph}/{container_id}",
                          params={"fields": "status_code", "access_token": token}, timeout=30).json()
        if st.get("status_code") == "FINISHED":
            return
        if st.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram odrzucił zdjęcie: {st}")
        time.sleep(3)


def _publish(graph, user_id, creation_id, token):
    r = requests.post(f"{graph}/{user_id}/media_publish",
                      data={"creation_id": creation_id, "access_token": token}, timeout=60)
    _check(r)
    return r.json()["id"]


def publish_photo(image_url, caption):
    graph, user_id, token = config.ig_host(), config.env("IG_USER_ID"), config.env("IG_ACCESS_TOKEN")
    r = requests.post(f"{graph}/{user_id}/media",
                      data={"image_url": image_url, "caption": caption, "access_token": token}, timeout=60)
    _check(r)
    creation_id = r.json()["id"]
    _wait_ready(graph, creation_id, token)
    return _publish(graph, user_id, creation_id, token)


def publish_carousel(image_urls, caption):
    """Karuzela 2-10 zdjęć: kontenery dzieci, kontener karuzeli, publikacja."""
    graph, user_id, token = config.ig_host(), config.env("IG_USER_ID"), config.env("IG_ACCESS_TOKEN")
    children = []
    for url in image_urls:
        r = requests.post(f"{graph}/{user_id}/media",
                          data={"image_url": url, "is_carousel_item": "true", "access_token": token}, timeout=60)
        _check(r)
        children.append(r.json()["id"])
    for child in children:
        _wait_ready(graph, child, token)
    r = requests.post(f"{graph}/{user_id}/media",
                      data={"media_type": "CAROUSEL", "children": ",".join(children),
                            "caption": caption, "access_token": token}, timeout=60)
    _check(r)
    creation_id = r.json()["id"]
    _wait_ready(graph, creation_id, token)
    return _publish(graph, user_id, creation_id, token)
