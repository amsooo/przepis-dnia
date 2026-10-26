"""Użycie: python -m src.main propose | poll

propose - raz dziennie: wymyśla przepis i wysyła podgląd na Telegram.
poll    - co kilka minut: odbiera kliknięcia i uwagi z Telegrama, poprawia lub publikuje.
"""
import sys
import traceback
from datetime import datetime, timezone

from . import config, image, instagram, recipe, state, telegram
from .state import ROOT


def _now():
    return datetime.now(timezone.utc)


def _make_pending(data, version_suffix):
    stamp = _now().strftime("%Y-%m-%d")
    rel = f"media/{stamp}-{version_suffix}.jpg"
    return rel


def _send_preview(pending):
    caption = recipe.build_caption(pending["recipe"])
    telegram.send_preview(ROOT / pending["image"], pending["recipe"]["title"], caption,
                          pending.get("image_note", ""))


def _make_image(pending, prompt):
    """Generuje zdjęcie; gdy zadziałał dostawca rezerwowy, dopisuje ostrzeżenie do podglądu."""
    provider, errors = image.generate(prompt, ROOT / pending["image"])
    if errors:
        pending["image_note"] = f"⚠️ Zdjęcie z generatora rezerwowego ({provider}), może mieć znak wodny. {errors[0][:250]}"
    else:
        pending["image_note"] = ""


def _titles():
    return [h["title"] for h in state.load_history()]


def _new_pending(st, version):
    data = recipe.generate(_titles())
    rel = _make_pending(data, version)
    st["pending"] = {"recipe": data, "image": rel, "status": "awaiting",
                     "version": version, "created": _now().isoformat()}
    _make_image(st["pending"], data["image_prompt"])
    _send_preview(st["pending"])


def propose():
    st = state.load_state()
    if st["pending"]:
        telegram.send_text("Poprzedni przepis nadal czeka na decyzję, więc dziś nie generuję nowego.")
        return
    _new_pending(st, 1)
    state.save_state(st)


def publish(st):
    p = st["pending"]
    url = f"{config.public_base_url()}/{p['image']}"
    post_id = instagram.publish_photo(url, recipe.build_caption(p["recipe"]))
    state.append_history({"date": _now().date().isoformat(), "title": p["recipe"]["title"],
                          "instagram_id": post_id})
    st["pending"] = None
    telegram.send_text(f"✅ Opublikowano: {p['recipe']['title']}")


def _handle_callback(st, cb):
    p = st["pending"]
    telegram.answer_callback(cb["id"])
    if not p:
        telegram.send_text("Nie ma niczego do zatwierdzenia.")
        return
    action = cb["data"]
    if action == "approve":
        publish(st)
    elif action == "edit":
        p["status"] = "awaiting_feedback"
        telegram.send_text("Napisz, co zmienić (np. „mniej ostre, dodaj gotowanie na parze, zdjęcie jaśniejsze”).")
    elif action == "new":
        _new_pending(st, p["version"] + 1)
    elif action == "image":
        p["version"] += 1
        p["image"] = _make_pending(p["recipe"], p["version"])
        _make_image(p, p["recipe"]["image_prompt"])
        _send_preview(p)


def _handle_message(st, msg):
    p = st["pending"]
    if not p or p["status"] != "awaiting_feedback" or "text" not in msg:
        return
    telegram.send_text("Poprawiam, chwilę…")
    new_recipe, regen = recipe.revise(p["recipe"], msg["text"])
    p["recipe"] = new_recipe
    p["version"] += 1
    if regen:
        p["image"] = _make_pending(new_recipe, p["version"])
        _make_image(p, new_recipe["image_prompt"])
    p["status"] = "awaiting"
    _send_preview(p)


def poll():
    st = state.load_state()
    allowed = telegram.chat_id()
    for upd in telegram.get_updates(st["telegram_offset"]):
        st["telegram_offset"] = upd["update_id"] + 1
        try:
            if "callback_query" in upd:
                cb = upd["callback_query"]
                if cb["from"]["id"] == allowed:  # tylko właściciel konta
                    _handle_callback(st, cb)
            elif "message" in upd:
                msg = upd["message"]
                if msg["chat"]["id"] == allowed:
                    _handle_message(st, msg)
        except Exception as exc:  # jedna wadliwa wiadomość nie może blokować kolejki
            traceback.print_exc()
            telegram.send_text(f"⚠️ Nie udało się obsłużyć ostatniej akcji: {str(exc)[:300]}")
    hours = config.auto_publish_after_hours()
    p = st["pending"]
    if hours and p and p["status"] == "awaiting":
        age = (_now() - datetime.fromisoformat(p["created"])).total_seconds() / 3600
        if age >= hours:
            publish(st)
    state.save_state(st)


if __name__ == "__main__":
    {"propose": propose, "poll": poll}[sys.argv[1]]()
