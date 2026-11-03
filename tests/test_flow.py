from datetime import datetime, timezone

import pytest

from src import main, recipe, state

RECIPE = {"title": "Szakszuka", "intro": "Jajka w sosie.", "time_min": 20, "servings": 2,
          "ingredients": ["4 jajka", "400 g pomidorów"], "steps": ["Podsmaż.", "Wbij jajka."],
          "tip": "", "hashtags": ["#szakszuka"], "image_prompt": "shakshuka"}


published = []


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "STATE", tmp_path / "state.json")
    monkeypatch.setattr(state, "HISTORY", tmp_path / "history.json")
    monkeypatch.setattr(main, "ROOT", tmp_path)
    (tmp_path / "history.json").write_text("[]")
    state.save_state({"pending": None, "telegram_offset": 0})
    sent = []
    published.clear()
    monkeypatch.setattr(main.telegram, "chat_id", lambda: 1)
    monkeypatch.setattr(main.telegram, "webhook_active", lambda: False)
    monkeypatch.delenv("UPDATE_JSON", raising=False)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")  # ręczne uruchomienie omija strażnika dziennego
    monkeypatch.setattr(main.telegram, "send_text", lambda t, k=None: sent.append(t))
    monkeypatch.setattr(main.telegram, "send_preview", lambda *a: sent.append("preview"))
    monkeypatch.setattr(main.telegram, "answer_callback", lambda *a: None)
    monkeypatch.setattr(main.image, "generate", lambda p, out: ("gemini", []))
    monkeypatch.setattr(main.recipe, "generate", lambda titles: dict(RECIPE))
    monkeypatch.setattr(main.instagram, "publish_photo", lambda url, cap: "ig123")
    monkeypatch.setattr(main.instagram, "publish_carousel", lambda urls, cap: published.append(urls) or "ig123")
    monkeypatch.setattr(main.instagram, "publish_reel", lambda url, cap: published.append([url]) or "igreel")
    monkeypatch.setattr(main.reel, "render", lambda *a, **k: None)
    monkeypatch.delenv("POST_FORMAT", raising=False)
    monkeypatch.setattr(main.config, "public_base_url", lambda: "https://x")
    return sent


def updates(monkeypatch, items):
    monkeypatch.setattr(main.telegram, "get_updates", lambda off: items)


def cb(data, uid=1, n=1):
    return {"update_id": n, "callback_query": {"id": "c", "data": data, "from": {"id": uid}}}


def test_propose_then_approve(env, monkeypatch):
    main.propose()
    assert state.load_state()["pending"]["status"] == "awaiting"
    updates(monkeypatch, [cb("approve")])
    main.poll()
    st = state.load_state()
    assert st["pending"] is None
    assert state.load_history()[0]["instagram_id"] == "ig123,igreel"


def test_edit_loop(env, monkeypatch):
    main.propose()
    updates(monkeypatch, [cb("edit")])
    main.poll()
    assert state.load_state()["pending"]["status"] == "awaiting_feedback"
    revised = dict(RECIPE, title="Szakszuka ostra")
    monkeypatch.setattr(main.recipe, "revise", lambda r, f: (revised, False))
    updates(monkeypatch, [{"update_id": 2, "message": {"chat_id": 1, "chat": {"id": 1}, "text": "ostrzej"}}])
    main.poll()
    p = state.load_state()["pending"]
    assert p["status"] == "awaiting" and p["recipe"]["title"] == "Szakszuka ostra"


def test_stranger_is_ignored(env, monkeypatch):
    main.propose()
    updates(monkeypatch, [cb("approve", uid=999)])
    main.poll()
    assert state.load_state()["pending"] is not None


def test_auto_publish_after_timeout(env, monkeypatch):
    main.propose()
    st = state.load_state()
    st["pending"]["created"] = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
    state.save_state(st)
    monkeypatch.setattr(main.config, "auto_publish_after_hours", lambda: 3)
    updates(monkeypatch, [])
    main.poll()
    assert state.load_state()["pending"] is None


def test_caption_limit():
    long = dict(RECIPE, steps=["x" * 300] * 20, hashtags=["#a"] * 20)
    assert len(recipe.build_caption(long)) <= 2200


def test_image_fallback(tmp_path, monkeypatch):
    import io
    from PIL import Image
    from src import image
    buf = io.BytesIO(); Image.new("RGB", (100, 200)).save(buf, "PNG")

    def boom(prompt):
        raise RuntimeError("429")

    monkeypatch.setattr(image.config, "image_providers", lambda: ["gemini", "pollinations"])
    monkeypatch.setattr(image, "PROVIDERS", {"gemini": boom, "pollinations": lambda p: buf.getvalue()})
    out = tmp_path / "x.jpg"
    image.generate("zupa", out)
    assert Image.open(out).size == (100, 125)


def test_model_pick():
    from src import gemini
    gc = ("generateContent",)
    models = [{"name": f"models/{n}", "supportedGenerationMethods": gc} for n in [
        "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3-flash-preview", "gemini-2.5-pro",
        "gemini-2.5-flash-image", "gemini-3-pro-image-preview", "gemini-2.5-flash-preview-tts"]]
    assert gemini.pick(models, "text") == "gemini-2.5-flash"      # stabilny przed preview
    assert gemini.pick(models, "image") == "gemini-2.5-flash-image"
    assert gemini.pick([], "text") is None


def test_image_button_and_fallback_note(env, monkeypatch):
    main.propose()
    monkeypatch.setattr(main.image, "generate", lambda p, out: ("pollinations", ["gemini: 429"]))
    updates(monkeypatch, [cb("image")])
    main.poll()
    p = state.load_state()["pending"]
    assert p["version"] == 2 and "pollinations" in p["image_note"] and p["status"] == "awaiting"


def test_gemini_retries_5xx_then_next_model(monkeypatch):
    from src import gemini
    monkeypatch.setattr(gemini.time, "sleep", lambda s: None)
    monkeypatch.setattr(gemini, "model_chain", lambda *a, **k: ["m1", "m2"])
    monkeypatch.setattr(gemini.config, "env", lambda *a, **k: "key")
    calls = []

    class R:
        def __init__(self, code): self.status_code, self.ok = code, code == 200
        def json(self): return {"ok": True}

    def post(url, **kw):
        calls.append(url.split("/models/")[1])
        return R(200 if "m2" in url else 503)

    monkeypatch.setattr(gemini.requests, "post", post)
    assert gemini.generate("text", "X", "f", {}) == {"ok": True}
    assert calls == ["m1:generateContent"] * 2 + ["m2:generateContent"]


def test_magnific_response_formats(monkeypatch):
    import base64
    from src import image
    raw = base64.b64encode(b"jpegbytes").decode()
    assert image._extract_image({"data": [{"base64": raw}]}) == b"jpegbytes"
    assert image._extract_image({"data": {"generated": [], "task_id": "x"}}) is None


def test_unconfigured_provider_is_skipped_silently(tmp_path, monkeypatch):
    import io
    from PIL import Image
    from src import image
    buf = io.BytesIO(); Image.new("RGB", (100, 100)).save(buf, "PNG")
    monkeypatch.delenv("MAGNIFIC_API_KEY", raising=False)
    monkeypatch.setattr(image.config, "image_providers", lambda: ["magnific", "pollinations"])
    monkeypatch.setattr(image, "PROVIDERS", {"magnific": lambda p: 1 / 0, "pollinations": lambda p: buf.getvalue()})
    name, errors = image.generate("zupa", tmp_path / "x.jpg")
    assert name == "pollinations" and errors == []


def test_failing_update_does_not_block_queue(env, monkeypatch):
    main.propose()
    monkeypatch.setattr(main, "publish", lambda st: 1 / 0)
    updates(monkeypatch, [cb("approve", n=7)])
    main.poll()
    st = state.load_state()
    assert st["telegram_offset"] == 8          # kliknięcie uznane za odebrane
    assert st["pending"] is not None           # przepis nadal czeka
    assert any("Nie udało się" in m for m in env)


def test_gemini_timeout_switches_to_next_model(monkeypatch):
    from src import gemini
    monkeypatch.setattr(gemini.time, "sleep", lambda s: None)
    monkeypatch.setattr(gemini, "model_chain", lambda *a, **k: ["m1", "m2"])
    monkeypatch.setattr(gemini.config, "env", lambda *a, **k: "key")
    calls = []

    class R:
        status_code, ok = 200, True
        def json(self): return {"ok": True}

    def post(url, **kw):
        calls.append(url.split("/models/")[1].split(":")[0])
        if "m1" in url:
            raise gemini.requests.Timeout()
        return R()

    monkeypatch.setattr(gemini.requests, "post", post)
    assert gemini.generate("text", "X", "f", {}) == {"ok": True}
    assert calls == ["m1", "m2"]                # timeout nie jest ponawiany na tym samym modelu


def test_magnific_async_task_formats():
    from src import image
    # odpowiedź z "data" (dokumentacja v5-pro) i z polami na wierzchu (v5-lite)
    assert image._extract_image({"data": {"task_id": "t", "status": "IN_PROGRESS", "generated": []}}) is None
    assert image._task({"task_id": "t", "status": "CREATED", "generated": []})["task_id"] == "t"
    assert image._task({"data": {"task_id": "t2"}})["task_id"] == "t2"


def test_carousel_published_with_both_slides(env, monkeypatch):
    main.propose()
    p = state.load_state()["pending"]
    assert p["card"].endswith("-skladniki.jpg")
    updates(monkeypatch, [cb("approve")])
    main.poll()
    assert len(published) == 2                                    # karuzela + reel (domyślnie both)
    assert len(published[0]) == 2 and published[1][0].endswith("-reel.mp4")
    assert published[0][0].endswith(p["image"]) and published[0][1].endswith(p["card"])


def test_hashtags_mix_and_cleaning():
    from datetime import date
    r = recipe.finalize_hashtags({"hashtags": ["#Zupa Fasolowa", "#żurek", "#ok"]}, "zupa", date(2026, 10, 28))
    tags = r["hashtags"]
    assert len(tags) == len(set(tags)) and len(tags) <= 7
    assert "#zupa" in tags and "#zurek" in tags and all(t.startswith("#") for t in tags)
    assert "#ok" not in tags            # za krótki, odrzucony


def test_card_renders_with_polish_text(tmp_path):
    from PIL import Image
    from src import card
    out = tmp_path / "c.jpg"
    card.render(dict(RECIPE, ingredients=["1 łyżka śmietany"] * 30), out)
    assert Image.open(out).size == (1080, 1350)


def test_token_reminder_windows():
    from datetime import date
    from src import reminders
    today = date(2026, 12, 1)
    assert reminders.token_notice("", today) is None
    assert reminders.token_notice("2026-10-26", today) is None            # 36 dni: jeszcze za wcześnie
    assert "za około 15 dni" in reminders.token_notice("2026-10-17", today)  # 45 dni
    assert "wygasa za około 0 dni" in reminders.token_notice("2026-10-02", today)  # 60 dni
    assert "już wygasł" in reminders.token_notice("2026-09-01", today)
    assert "zły format" in reminders.token_notice("wczoraj", today)


def test_propose_sends_token_notice(env, monkeypatch):
    monkeypatch.setenv("IG_TOKEN_DATE", "2000-01-01")
    main.propose()
    assert any("Token Instagrama" in m for m in env)


def test_single_update_from_worker(env, monkeypatch):
    import json
    main.propose()
    monkeypatch.setenv("UPDATE_JSON", json.dumps(cb("approve", n=50)))
    monkeypatch.setattr(main.telegram, "get_updates", lambda off: 1 / 0)   # nie wolno odpytywać Telegrama
    main.poll()
    st = state.load_state()
    assert st["pending"] is None and st["last_update_id"] == 50
    assert len(published) == 2


def test_duplicate_update_ignored(env, monkeypatch):
    import json
    main.propose()
    monkeypatch.setenv("UPDATE_JSON", json.dumps(cb("approve", n=60)))
    main.poll()
    main.propose()                                     # nowy przepis czeka na decyzję
    main.poll()                                        # ta sama akcja dostarczona drugi raz
    assert len(published) == 2 and state.load_state()["pending"] is not None


def test_webhook_mode_scheduled_run_does_not_poll(env, monkeypatch):
    monkeypatch.setattr(main.telegram, "webhook_active", lambda: True)
    monkeypatch.setattr(main.telegram, "get_updates", lambda off: 1 / 0)
    main.poll()                                        # nie rzuca wyjątku, bo nie pyta o akcje


def test_scheduled_retry_is_silent_when_already_proposed(env, monkeypatch):
    monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")
    main.propose()
    before = len(env)
    main.propose()                                      # ponowna próba z harmonogramu tego samego dnia
    assert len(env) == before                           # nic nowego na Telegramie
    assert state.load_state()["last_proposed"]


def test_generation_failure_notifies_and_allows_retry(env, monkeypatch):
    monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")
    monkeypatch.setattr(main.recipe, "generate", lambda titles: (_ for _ in ()).throw(RuntimeError("Gemini 503")))
    with pytest.raises(RuntimeError):
        main.propose()
    assert any("Nie udało się wygenerować" in m for m in env)
    assert state.load_state().get("last_proposed") is None   # kolejna próba nie jest zablokowana


def test_post_format_selection(env, monkeypatch):
    monkeypatch.setenv("POST_FORMAT", "reel")
    main.propose()
    updates(monkeypatch, [cb("approve")])
    main.poll()
    assert len(published) == 1 and published[0][0].endswith("-reel.mp4")


def test_partial_publish_resumes_without_duplicates(env, monkeypatch):
    main.propose()
    def boom(url, cap):
        raise RuntimeError("Instagram 400: reel odrzucony")
    monkeypatch.setattr(main.instagram, "publish_reel", boom)
    updates(monkeypatch, [cb("approve", n=1)])
    main.poll()
    st = state.load_state()
    assert st["pending"]["published"] == {"carousel": "ig123"}        # karuzela poszła, reel nie
    assert any("Nie udało się" in m for m in env)
    monkeypatch.setattr(main.instagram, "publish_reel", lambda url, cap: published.append([url]) or "igreel")
    updates(monkeypatch, [cb("approve", n=2)])
    main.poll()
    assert state.load_state()["pending"] is None
    assert len([u for u in published if len(u) == 2]) == 1             # karuzela tylko raz


def test_caption_hook_and_five_hashtags():
    r = dict(RECIPE, hook="Szybki obiad w 20 minut: szakszuka z jajkami")
    r = recipe.finalize_hashtags(dict(r, hashtags=["#szakszuka", "#jajka", "#trzeci"]), "zupa")
    cap = recipe.build_caption(r)
    assert cap.splitlines()[0] == "Szybki obiad w 20 minut: szakszuka z jajkami"
    assert len(r["hashtags"]) <= 5 and "Zapisz ten przepis" in cap
    assert len(cap) <= 2200


def test_music_requires_key_and_writes_file(tmp_path, monkeypatch):
    from src import music
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    assert music.generate(tmp_path / "a.mp3", 12) is False

    sent = {}

    class R:
        ok, status_code, content, text = True, 200, b"MP3DATA", ""

    def post(url, **kw):
        sent.update(url=url, **kw)
        return R()

    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    monkeypatch.setattr(music.requests, "post", post)
    assert music.generate(tmp_path / "b.mp3", 13) is True
    assert (tmp_path / "b.mp3").read_bytes() == b"MP3DATA"
    assert sent["json"]["force_instrumental"] is True and sent["json"]["music_length_ms"] == 14000
    assert sent["headers"]["xi-api-key"] == "k" and sent["url"].endswith("/v1/music")


def test_music_library_roundtrip_and_rotation(tmp_path, monkeypatch):
    from src import music
    monkeypatch.setenv("MUSIC_KEY", "tajny-klucz")
    monkeypatch.setattr(music, "LIBRARY", tmp_path)
    for i in (1, 2, 3):
        raw = tmp_path / f"r{i}.mp3"
        raw.write_bytes(b"AUDIO" + bytes([i]))
        music.encrypt_file(raw, tmp_path / f"track-{i:02d}.mp3.enc")
    tracks = music.library()
    assert [t.name for t in tracks] == ["track-01.mp3.enc", "track-02.mp3.enc", "track-03.mp3.enc"]
    assert b"AUDIO" not in tracks[0].read_bytes()                  # w repo leży szyfrogram
    music.decrypt_to(music.pick(tracks, 4), tmp_path / "out.mp3")  # 4 % 3 = 1, czyli druga ścieżka
    assert (tmp_path / "out.mp3").read_bytes() == b"AUDIO\x02"
    monkeypatch.setenv("MUSIC_KEY", "inny")
    with pytest.raises(Exception):
        music.decrypt_to(tracks[0], tmp_path / "zly.mp3")          # zły klucz nie odszyfruje
    assert music.pick([], 5) is None


def test_music_old_key_still_works_after_adding_music_key(tmp_path, monkeypatch):
    from src import music
    monkeypatch.setattr(music, "LIBRARY", tmp_path)
    monkeypatch.delenv("MUSIC_KEY", raising=False)
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "zapasowy")
    raw = tmp_path / "r.mp3"; raw.write_bytes(b"AUDIO")
    music.encrypt_file(raw, tmp_path / "track-01.mp3.enc")          # biblioteka powstała przed dodaniem MUSIC_KEY
    monkeypatch.setenv("MUSIC_KEY", "nowy")                          # dodajemy MUSIC_KEY później
    assert music.decrypt_to(tmp_path / "track-01.mp3.enc", tmp_path / "o.mp3") == "TELEGRAM_WEBHOOK_SECRET"
    assert (tmp_path / "o.mp3").read_bytes() == b"AUDIO"


def test_video_uses_library_track_and_survives_failures(env, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(main.reel, "render", lambda *a, **k: calls.append(k.get("audio_path")))
    fake = tmp_path / "track-01.mp3.enc"; fake.write_bytes(b"x")
    monkeypatch.setattr(main.music, "library", lambda: [fake])
    monkeypatch.setattr(main.music, "decrypt_to", lambda src, dst: pathlib_write(dst))
    main.propose()
    assert calls and calls[-1] is not None                          # podkład trafił do montażu
    p = state.load_state()["pending"]

    def boom(src, dst):
        raise RuntimeError("zły klucz")
    monkeypatch.setattr(main.music, "decrypt_to", boom)
    main._make_video(p)
    assert calls[-1] is None and p["video"] and any("bez muzyki" in m for m in env)

    monkeypatch.setattr(main.music, "library", lambda: [])          # pusta biblioteka: cicho, bez wywołań API
    monkeypatch.setattr(main.music, "generate", lambda *a, **k: 1 / 0)
    main._make_video(p)
    assert calls[-1] is None
    monkeypatch.setenv("REEL_MUSIC", "0")
    n = len(calls); main._make_video(p)
    assert calls[-1] is None and len(calls) == n + 1


def pathlib_write(dst):
    import pathlib as _p
    _p.Path(dst).write_bytes(b"audio")


def test_music_styles_rotate():
    from datetime import date
    from src import music
    assert music.style_for(date(2026, 11, 3)) != music.style_for(date(2026, 11, 4))


def test_rekey_moves_library_to_music_key(tmp_path, monkeypatch):
    from src import music
    monkeypatch.setattr(music, "LIBRARY", tmp_path)
    monkeypatch.delenv("MUSIC_KEY", raising=False)
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "zapasowy")
    raw = tmp_path / "r.mp3"; raw.write_bytes(b"AUDIO")
    f = tmp_path / "track-01.mp3.enc"
    music.encrypt_file(raw, f)
    monkeypatch.setenv("MUSIC_KEY", "nowy")
    assert music.rekey(f) is True and music.rekey(f) is False          # drugi raz nic do roboty
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "zupelnie-inny")      # zmiana sekretu webhooka już niczego nie psuje
    assert music.decrypt_to(f, tmp_path / "o.mp3") == "MUSIC_KEY"
    assert (tmp_path / "o.mp3").read_bytes() == b"AUDIO"


def test_model_chain_reaches_older_and_lite_models():
    from src import gemini
    gc = ("generateContent",)
    names = ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.1-flash-lite",
             "gemini-3.8-flash-preview", "gemini-3.1-flash-image", "gemini-3.1-flash-lite-image"]
    models = [{"name": f"models/{n}", "supportedGenerationMethods": gc} for n in names]
    text = gemini.ranked(models, "text")
    assert text[:3] == ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-2.5-flash"]   # stabilne nie-lite, od najnowszego
    assert text.index("gemini-2.5-flash") < text.index("gemini-3.1-flash-lite")        # lite dopiero na końcu
    assert text.index("gemini-3.8-flash-preview") < text.index("gemini-2.5-flash-lite")
    assert gemini.ranked(models, "image") == ["gemini-3.1-flash-image"]                  # obrazy bez lite
