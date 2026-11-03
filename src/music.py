"""Podkład muzyczny do Reela: biblioteka ścieżek z ElevenLabs (Eleven Music), generowana raz.

Repo jest publiczne, więc ścieżki leżą w `assets/music/` ZASZYFROWANE (Fernet); klucz pochodzi z sekretu MUSIC_KEY
(a gdy go brak, z TELEGRAM_WEBHOOK_SECRET). Odszyfrowany plik żyje tylko w katalogu tymczasowym i trafia do mp4.
Bez biblioteki film jest cichy.
"""
import base64
import hashlib
from datetime import date
from pathlib import Path

import requests
from cryptography.fernet import Fernet, InvalidToken

from . import config

LIBRARY = Path(__file__).resolve().parent.parent / "assets" / "music"

# Rotacja klimatów, żeby kolejne Reele nie brzmiały tak samo.
STYLES = [
    "warm acoustic guitar with light percussion, cozy morning kitchen mood",
    "mellow lo-fi beat with soft piano and vinyl warmth, relaxed cooking show",
    "upbeat ukulele with gentle handclaps, cheerful food video",
    "smooth bossa nova with brushed drums and upright bass, lazy Sunday brunch",
    "light acoustic folk with playful banjo, sunny and friendly",
    "soft pop instrumental with warm synth pads and a gentle groove, modern and clean",
    "gentle jazz trio with piano, upright bass and brushed snare, relaxed cafe atmosphere",
    "fingerstyle acoustic guitar with soft strings, calm and elegant dinner preparation",
    "light funky groove with clean electric guitar and bouncy bass, playful kitchen energy",
    "dreamy piano with ambient pads and a soft pulse, relaxing evening cooking",
]
SUFFIX = "Instrumental only, no vocals, steady background track suitable under a recipe video, no abrupt changes."


def style_for(today=None):
    return STYLES[(today or date.today()).toordinal() % len(STYLES)]


def generate(out_path, seconds, today=None, style=None):
    """Zapisuje mp3 o długości ok. `seconds` s; zwraca False, gdy nie ma klucza."""
    key = config.env("ELEVENLABS_API_KEY", "", required=False)
    if not key:
        return False
    resp = requests.post(
        "https://api.elevenlabs.io/v1/music",
        headers={"xi-api-key": key, "Content-Type": "application/json"},
        params={"output_format": "mp3_44100_128"},
        json={"prompt": f"{style or style_for(today)}. {SUFFIX}",
              "music_length_ms": max(10000, int(seconds * 1000) + 1000),
              "force_instrumental": True},
        timeout=180,
    )
    if not resp.ok:
        # komunikat błędu ElevenLabs nie zawiera klucza; pomaga zdiagnozować plan/limity
        raise RuntimeError(f"ElevenLabs {resp.status_code}: {resp.text[:200]}")
    out_path.write_bytes(resp.content)
    return True


def _fernets():
    """Klucze do prób: najpierw MUSIC_KEY, potem zapasowy TELEGRAM_WEBHOOK_SECRET (biblioteka mogła powstać przed dodaniem MUSIC_KEY)."""
    keys = []
    for name in ("MUSIC_KEY", "TELEGRAM_WEBHOOK_SECRET"):
        secret = config.env(name, "", required=False)
        if secret:
            raw = hashlib.pbkdf2_hmac("sha256", secret.encode(), b"przepis-dnia-music", 200_000, 32)
            keys.append((name, Fernet(base64.urlsafe_b64encode(raw))))
    if not keys:
        raise RuntimeError("Brak MUSIC_KEY (ani TELEGRAM_WEBHOOK_SECRET): nie da się zaszyfrować/odszyfrować podkładów")
    return keys


def encrypt_file(src, dst):
    Path(dst).write_bytes(_fernets()[0][1].encrypt(Path(src).read_bytes()))


def decrypt_to(src, dst):
    """Odszyfrowuje plik pierwszym pasującym kluczem; zwraca nazwę użytego sekretu."""
    data = Path(src).read_bytes()
    for name, fernet in _fernets():
        try:
            Path(dst).write_bytes(fernet.decrypt(data))
            return name
        except InvalidToken:
            continue
    raise RuntimeError("Żaden dostępny klucz nie odszyfrowuje podkładu")


def library():
    """Zaszyfrowane ścieżki z biblioteki w stałej kolejności."""
    return sorted(LIBRARY.glob("track-*.mp3.enc"))


def pick(tracks, index):
    """Kolejne posty dostają kolejne ścieżki (index = liczba dotychczasowych publikacji)."""
    return tracks[index % len(tracks)] if tracks else None
