from datetime import datetime, timezone

import pytest

from src import main, recipe, state

RECIPE = {"title": "Szakszuka", "intro": "Jajka w sosie.", "time_min": 20, "servings": 2,
          "ingredients": ["4 jajka", "400 g pomidorów"], "steps": ["Podsmaż.", "Wbij jajka."],
          "tip": "", "hashtags": ["#szakszuka"], "image_prompt": "shakshuka"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "STATE", tmp_path / "state.json")
    monkeypatch.setattr(state, "HISTORY", tmp_path / "history.json")
    monkeypatch.setattr(main, "ROOT", tmp_path)
    (tmp_path / "history.json").write_text("[]")
    state.save_state({"pending": None, "telegram_offset": 0})
    sent = []
    monkeypatch.setattr(main.telegram, "chat_id", lambda: 1)
    monkeypatch.setattr(main.telegram, "send_text", lambda t, k=None: sent.append(t))
    monkeypatch.setattr(main.telegram, "send_preview", lambda *a: sent.append("preview"))
    monkeypatch.setattr(main.telegram, "answer_callback", lambda *a: None)
    monkeypatch.setattr(main.image, "generate", lambda p, out: ("gemini", []))
    monkeypatch.setattr(main.recipe, "generate", lambda titles: dict(RECIPE))
    monkeypatch.setattr(main.instagram, "publish_photo", lambda url, cap: "ig123")
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
    assert state.load_history()[0]["instagram_id"] == "ig123"


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
