import time

import requests

from . import config

# Domyślnie logowanie przez Facebooka (token strony). Dla "Instagram API with Instagram Login"
# ustaw IG_GRAPH_HOST=https://graph.instagram.com/v21.0 (token z panelu aplikacji, ważny 60 dni).
GRAPH = config.env("IG_GRAPH_HOST", "https://graph.facebook.com/v21.0", required=False)


def publish_photo(image_url, caption):
    user_id = config.env("IG_USER_ID")
    token = config.env("IG_ACCESS_TOKEN")
    r = requests.post(f"{GRAPH}/{user_id}/media",
                      data={"image_url": image_url, "caption": caption, "access_token": token}, timeout=60)
    r.raise_for_status()
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
    r.raise_for_status()
    return r.json()["id"]
