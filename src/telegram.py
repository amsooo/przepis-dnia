import requests

from . import config


def _call(method, **payload):
    token = config.env("TELEGRAM_BOT_TOKEN")
    resp = requests.post(f"https://api.telegram.org/bot{token}/{method}", json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()["result"]


def chat_id():
    return int(config.env("TELEGRAM_CHAT_ID"))


def send_text(text, keyboard=None):
    payload = {"chat_id": chat_id(), "text": text}
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}
    return _call("sendMessage", **payload)


def send_photo(path, caption):
    token = config.env("TELEGRAM_BOT_TOKEN")
    with open(path, "rb") as fh:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendPhoto",
            data={"chat_id": chat_id(), "caption": caption[:1024]},
            files={"photo": fh},
            timeout=120,
        )
    resp.raise_for_status()
    return resp.json()["result"]


def send_preview(image_path, title, caption, note="", card_path=None):
    send_photo(image_path, f"{note}\n\n{title}" if note else title)
    if card_path:
        send_photo(card_path, "Slajd 2: składniki")
    keyboard = [[
        {"text": "✅ Akceptuj", "callback_data": "approve"},
        {"text": "✏️ Popraw", "callback_data": "edit"},
        {"text": "🔄 Inny przepis", "callback_data": "new"},
    ], [
        {"text": "🖼 Inne zdjęcie", "callback_data": "image"},
    ]]
    return send_text(caption, keyboard)


def get_updates(offset):
    return _call("getUpdates", offset=offset, timeout=0, allowed_updates=["message", "callback_query"])


def answer_callback(callback_id, text=""):
    # Telegram przyjmuje odpowiedź tylko przez chwilę po kliknięciu; przy opóźnionym odbiorze 400 jest normalny.
    try:
        _call("answerCallbackQuery", callback_query_id=callback_id, text=text)
    except requests.HTTPError:
        pass


def webhook_active():
    """Gdy webhook jest ustawiony, Telegram nie pozwala na getUpdates: kliknięcia przychodzą z Workera."""
    return bool(_call("getWebhookInfo").get("url"))
