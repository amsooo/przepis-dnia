"""Jednorazowa konfiguracja Instagrama. Użycie: python -m src.ig_setup

Wymienia krótkotrwały token użytkownika na długoterminowy, znajduje strony z kontem Instagram
i wysyła IG_USER_ID oraz token strony (nie wygasa) na Twój czat Telegram. Nic z tego nie trafia do logów.
"""
import os
import sys

import requests

GRAPH = "https://graph.facebook.com/v21.0"


def _send(text):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": int(os.environ["TELEGRAM_CHAT_ID"]), "text": text}, timeout=60)
    r.raise_for_status()


def main():
    r = requests.get(f"{GRAPH}/oauth/access_token", params={
        "grant_type": "fb_exchange_token",
        "client_id": os.environ["IG_APP_ID"],
        "client_secret": os.environ["IG_APP_SECRET"],
        "fb_exchange_token": os.environ["IG_SHORT_TOKEN"],
    }, timeout=60)
    if not r.ok:
        # tekst błędu Meta nie zawiera sekretów; wysyłamy go, żeby było wiadomo co poprawić
        _send(f"❌ Meta odrzuciła token: {r.text[:300]}")
        sys.exit("Wymiana tokenu nie powiodła się (szczegóły na Telegramie).")
    long_token = r.json()["access_token"]
    pages = requests.get(f"{GRAPH}/me/accounts", params={
        "fields": "name,access_token,instagram_business_account{id,username}",
        "access_token": long_token}, timeout=60).json().get("data", [])
    found = [p for p in pages if p.get("instagram_business_account")]
    if not found:
        _send("❌ Nie znaleziono strony Facebooka połączonej z kontem Instagram. Sprawdź, czy konto IG jest "
              "biznesowe/twórcy i połączone ze stroną oraz czy token ma uprawnienia pages_show_list, "
              "pages_read_engagement i instagram_basic (przy stronie w portfolio biznesowym także business_management).")
        sys.exit("Brak stron z kontem Instagram.")
    for p in found:
        ig = p["instagram_business_account"]
        _send(f"✅ Strona: {p['name']}  |  Instagram: @{ig.get('username', '?')}\n\n"
              f"IG_USER_ID:\n{ig['id']}\n\nIG_ACCESS_TOKEN:\n{p['access_token']}\n\n"
              "Wpisz oba jako secrets w repo, a potem usuń tę wiadomość z czatu.")
    print(f"Wysłano dane {len(found)} konta(-ek) na Telegram.")


if __name__ == "__main__":
    main()
