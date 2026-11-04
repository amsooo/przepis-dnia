"""Użycie: python -m src.main propose | poll

propose - raz dziennie: wymyśla przepis i wysyła podgląd na Telegram.
poll    - co kilka minut: odbiera kliknięcia i uwagi z Telegrama, poprawia lub publikuje.
"""
import json
import sys
import tempfile
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import card, config, image, instagram, music, recipe, reel, reminders, state, telegram
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
                          pending.get("image_note", ""),
                          ROOT / pending["card"] if pending.get("card") else None,
                          ROOT / pending["video"] if pending.get("video") else None)


def _make_video(pending):
    """Reel zależy od zdjęcia i karty, więc powstaje po każdej ich zmianie. Awaria filmu nie blokuje karuzeli,
    a awaria muzyki oznacza tylko cichy film."""
    pending["video"] = f"media/{_now().strftime('%Y-%m-%d')}-{pending['version']}-reel.mp4"
    with tempfile.TemporaryDirectory() as tmp:
        audio = None
        if (config.env("REEL_MUSIC", "", required=False) or "1") != "0":
            try:
                track = music.pick(music.library(), len(state.load_history()))
                if track:
                    audio = Path(tmp) / "podklad.mp3"
                    music.decrypt_to(track, audio)
            except Exception as exc:
                traceback.print_exc()
                audio = None
                telegram.send_text(f"⚠️ Reel bez muzyki (podkład się nie odszyfrował): {str(exc)[:200]}")
        try:
            reel.render(ROOT / pending["image"], ROOT / pending["card"], pending["recipe"],
                        ROOT / pending["video"], audio_path=audio)
        except Exception as exc:
            traceback.print_exc()
            pending["video"] = None
            telegram.send_text(f"⚠️ Nie udało się zrobić Reela (karuzela działa): {str(exc)[:200]}")


def _make_card(pending):
    """Slajd 2 zależy od przepisu, więc powstaje na nowo za każdym razem, gdy przepis się zmienia."""
    pending["card"] = f"media/{_now().strftime('%Y-%m-%d')}-{pending['version']}-skladniki.jpg"
    (ROOT / pending["card"]).parent.mkdir(parents=True, exist_ok=True)
    card.render(pending["recipe"], ROOT / pending["card"])


def _make_image(pending, prompt):
    """Generuje zdjęcie; gdy zadziałał dostawca rezerwowy, dopisuje ostrzeżenie do podglądu."""
    provider, errors = image.generate(f"{prompt} {recipe.IMAGE_RULES}", ROOT / pending["image"])
    if errors:
        pending["image_note"] = f"⚠️ Zdjęcie z generatora rezerwowego ({provider}), może mieć znak wodny. {errors[0][:250]}"
    else:
        pending["image_note"] = ""


def _titles():
    return [h["title"] for h in state.load_history()]


QUEUE_TARGET = 5  # ile gotowych przepisów trzymamy w zapasie na wypadek awarii Gemini


def _next_recipe(st):
    """Przepis z zapasu (natychmiast), a gdy go brak, świeżo wygenerowany."""
    queue = st.setdefault("queue", [])
    if queue:
        return queue.pop(0)
    return recipe.generate(_titles())


def _refill(st, limit=3):
    """Uzupełnia zapas, dopóki Gemini odpowiada. Pierwszy błąd przerywa, bo awarie trwają godzinami."""
    queue = st.setdefault("queue", [])
    made = 0
    while len(queue) < QUEUE_TARGET and made < limit:
        taken = _titles() + [r["title"] for r in queue]
        try:
            queue.append(recipe.generate(taken, today=_now().date() + timedelta(days=len(queue) + 1), budget=100))
        except Exception as exc:
            print(f"[zapas] nie udało się uzupełnić: {exc}", file=sys.stderr)
            break
        made += 1
    return made


def refill():
    """Osobne uruchomienie (w nocy, gdy Gemini zwykle jest mniej obciążony): dobija zapas do pełna."""
    st = state.load_state()
    made = _refill(st, limit=QUEUE_TARGET)
    state.save_state(st)
    print(f"[zapas] dodano {made}, w zapasie {len(st['queue'])}")
    if not made and len(st["queue"]) < 2:
        telegram.send_text(f"ℹ️ Zapas przepisów jest mały ({len(st['queue'])}); pewnie Gemini jest przeciążony.")


def _new_pending(st, version):
    data = _next_recipe(st)
    rel = _make_pending(data, version)
    st["pending"] = {"recipe": data, "image": rel, "status": "awaiting",
                     "version": version, "created": _now().isoformat()}
    _make_image(st["pending"], data["image_prompt"])
    _make_card(st["pending"])
    _make_video(st["pending"])
    _send_preview(st["pending"])


def propose():
    notice = reminders.token_notice(config.env("IG_TOKEN_DATE", "", required=False))
    if notice:
        telegram.send_text(notice)
    st = state.load_state()
    today = _now().date().isoformat()
    manual = config.env("GITHUB_EVENT_NAME", "", required=False) == "workflow_dispatch"
    if st.get("last_proposed") == today and not manual:
        return  # dzisiejszy przepis już był (ponowne próby z harmonogramu są wtedy ciche)
    if st["pending"]:
        telegram.send_text("Poprzedni przepis nadal czeka na decyzję, więc dziś nie generuję nowego.")
        st["last_proposed"] = today
        state.save_state(st)
        return
    try:
        _new_pending(st, 1)
    except Exception as exc:
        telegram.send_text(f"⚠️ Nie udało się wygenerować dzisiejszego przepisu: {str(exc)[:300]}\n"
                           "Spróbuję jeszcze raz później; możesz też ręcznie uruchomić „Codzienny przepis”.")
        raise
    st["last_proposed"] = today
    state.save_state(st)  # uzupełnianie zapasu to osobny krok workflow'u, żeby nie opóźniać zapisu stanu


def publish(st):
    p = st["pending"]
    base = config.public_base_url()
    caption = recipe.build_caption(p["recipe"])
    done = p.setdefault("published", {})     # po awarii w połowie nie dublujemy już opublikowanych formatów
    for fmt in config.post_formats():
        if fmt in done:
            continue
        if fmt == "reel" and not p.get("video"):
            continue
        if fmt == "reel":
            done[fmt] = instagram.publish_reel(f"{base}/{p['video']}", caption)
        elif p.get("card"):
            done[fmt] = instagram.publish_carousel([f"{base}/{p['image']}", f"{base}/{p['card']}"], caption)
        else:  # przepis przygotowany jeszcze przed wprowadzeniem karuzeli
            done[fmt] = instagram.publish_photo(f"{base}/{p['image']}", caption)
    state.append_history({"date": _now().date().isoformat(), "title": p["recipe"]["title"],
                          "instagram_id": ",".join(done.values())})
    st["pending"] = None
    telegram.send_text(f"✅ Opublikowano ({', '.join(done)}): {p['recipe']['title']}")


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
        _make_card(p)  # przepisy sprzed karuzeli dostają kartę przy okazji
        _make_video(p)
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
    _make_card(p)
    _make_video(p)
    p["status"] = "awaiting"
    _send_preview(p)


def _incoming(st):
    """Akcje do obsłużenia: pojedyncza z Workera (UPDATE_JSON), brak w trybie webhooka, inaczej getUpdates."""
    raw = config.env("UPDATE_JSON", "", required=False)
    if raw:
        return [json.loads(raw)]
    if telegram.webhook_active():
        return []  # w trybie webhooka akcje przychodzą pojedynczo z Workera
    updates = telegram.get_updates(st["telegram_offset"])
    print(f"[poll] odebrano {len(updates)} akcji z Telegrama (offset {st['telegram_offset']})")
    return updates


def poll():
    st = state.load_state()
    allowed = telegram.chat_id()
    for upd in _incoming(st):
        uid = upd["update_id"]
        st["telegram_offset"] = max(st["telegram_offset"], uid + 1)
        if uid <= st.get("last_update_id", -1):
            continue  # ta akcja była już obsłużona (ponowne dostarczenie przez Telegram)
        st["last_update_id"] = uid
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
    {"propose": propose, "poll": poll, "refill": refill}[sys.argv[1]]()
