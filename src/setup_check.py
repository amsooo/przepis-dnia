"""Pomoc przy konfiguracji. Użycie: python -m src.setup_check whoami | check

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
    if os.environ.get("TELEGRAM_CHAT_ID"):
        _api("sendMessage", chat_id=int(os.environ["TELEGRAM_CHAT_ID"]), text=f"Bot działa ✅\n{status}")


if __name__ == "__main__":
    {"whoami": whoami, "check": check}[sys.argv[1]]()
