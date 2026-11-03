"""Podkład muzyczny do Reela z ElevenLabs (Eleven Music), generowany przy każdym filmie.

Ścieżki NIE trafiają do repo (jest publiczne): powstają w katalogu tymczasowym i są miksowane tylko do pliku wideo.
Bez klucza ELEVENLABS_API_KEY film jest cichy.
"""
from datetime import date

import requests

from . import config

# Rotacja klimatów, żeby kolejne Reele nie brzmiały tak samo.
STYLES = [
    "warm acoustic guitar with light percussion, cozy morning kitchen mood",
    "mellow lo-fi beat with soft piano and vinyl warmth, relaxed cooking show",
    "upbeat ukulele with gentle handclaps, cheerful food video",
    "smooth bossa nova with brushed drums and upright bass, lazy Sunday brunch",
    "light acoustic folk with playful banjo, sunny and friendly",
    "soft pop instrumental with warm synth pads and a gentle groove, modern and clean",
]
SUFFIX = "Instrumental only, no vocals, steady background track suitable under a recipe video, no abrupt changes."


def style_for(today=None):
    return STYLES[(today or date.today()).toordinal() % len(STYLES)]


def generate(out_path, seconds, today=None):
    """Zapisuje mp3 o długości ok. `seconds` s; zwraca False, gdy nie ma klucza."""
    key = config.env("ELEVENLABS_API_KEY", "", required=False)
    if not key:
        return False
    resp = requests.post(
        "https://api.elevenlabs.io/v1/music",
        headers={"xi-api-key": key, "Content-Type": "application/json"},
        params={"output_format": "mp3_44100_128"},
        json={"prompt": f"{style_for(today)}. {SUFFIX}",
              "music_length_ms": max(10000, int(seconds * 1000) + 1000),
              "force_instrumental": True},
        timeout=180,
    )
    if not resp.ok:
        # komunikat błędu ElevenLabs nie zawiera klucza; pomaga zdiagnozować plan/limity
        raise RuntimeError(f"ElevenLabs {resp.status_code}: {resp.text[:200]}")
    out_path.write_bytes(resp.content)
    return True
