import os


def env(name, default=None, required=True):
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f"Brak zmiennej środowiskowej {name}")
    return value


def text_model():
    from . import gemini
    return gemini.model_for("text", "TEXT_MODEL", "gemini-2.5-flash")


def image_model():
    from . import gemini
    return gemini.model_for("image", "IMAGE_MODEL", "gemini-2.5-flash-image")


def image_providers():
    """Kolejność prób generowania zdjęcia; pierwszy, który zadziała, wygrywa."""
    return env("IMAGE_PROVIDERS", "magnific,gemini,pollinations", required=False).split(",")


def auto_publish_after_hours():
    """0 = nigdy nie publikuj bez kliknięcia Akceptuj."""
    return float(env("AUTO_PUBLISH_AFTER_HOURS", "0", required=False))


def public_base_url():
    # IG pobiera zdjęcie z publicznego URL-a; domyślnie raw.githubusercontent.com
    repo = env("GITHUB_REPOSITORY")
    branch = env("PUBLIC_BRANCH", "main", required=False)
    return f"https://raw.githubusercontent.com/{repo}/{branch}"
