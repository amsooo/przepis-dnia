"""Pomoc przy konfiguracji. Użycie: python -m src.setup_check whoami | check | models

whoami - odpowiada na Telegramie Twoim chat_id (nie trafia do logów Actions).
check  - sprawdza, których sekretów brakuje, i wysyła wiadomość testową.
"""
import os
import sys

import requests

SECRETS = ["GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "IG_USER_ID", "IG_ACCESS_TOKEN"]


def _api(method, **payload):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    resp = requests.post(f"https://api.telegram.org/bot{token}/{method}", json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()["result"]


def whoami():
    seen = {u["message"]["chat"]["id"] for u in _api("getUpdates") if "message" in u}
    if not seen:
        sys.exit("Brak wiadomości do bota. Otwórz bota w Telegramie, kliknij Start, napisz „cześć” i odpal ponownie.")
    for chat in seen:
        _api("sendMessage", chat_id=chat,
             text=f"Twoje chat_id to: {chat}\nWpisz je w repo jako secret TELEGRAM_CHAT_ID.")
    print(f"Wysłano chat_id do {len(seen)} czat(ów) na Telegramie.")


def check():
    missing = [name for name in SECRETS if not os.environ.get(name)]
    status = "Brakuje sekretów: " + ", ".join(missing) if missing else "Wszystkie sekrety są ustawione."
    print(status)  # same nazwy, bez wartości
    if os.environ.get("IG_USER_ID") and os.environ.get("IG_ACCESS_TOKEN"):
        from . import config
        host = config.ig_host()
        r = requests.get(f"{host}/{os.environ['IG_USER_ID']}",
                         params={"fields": "username", "access_token": os.environ["IG_ACCESS_TOKEN"]}, timeout=60)
        if r.ok:
            status += f"\nInstagram: @{r.json().get('username')} ✅"
            print("Instagram: OK")
        else:  # komunikat błędu Meta nie zawiera tokenu
            reason = r.json().get("error", {}).get("message", r.text[:200]) if r.headers.get("content-type", "").startswith(("application/json", "text/javascript")) else r.text[:200]
            status += f"\nInstagram: błąd {r.status_code} ❌ ({host.split('//')[1].split('/')[0]}): {reason}"
            print("Instagram: błąd", r.status_code, reason)
    if os.environ.get("TELEGRAM_CHAT_ID"):
        _api("sendMessage", chat_id=int(os.environ["TELEGRAM_CHAT_ID"]), text=f"Bot działa ✅\n{status}")


def models():
    """Wypisuje modele Gemini dostępne dla klucza oraz te wybrane automatycznie."""
    from . import config, gemini
    available = gemini.list_models()
    for m in available:
        if "generateContent" in m["supportedGenerationMethods"]:
            print(m["name"])
    print("Wybrany tekst:", config.text_model())
    print("Wybrany obraz:", config.image_model())


if __name__ == "__main__":
    {"whoami": whoami, "check": check, "models": models}[sys.argv[1]]()
