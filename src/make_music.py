"""Jednorazowo generuje bibliotekę podkładów. Użycie: python -m src.make_music [liczba]"""
import sys
import tempfile
from pathlib import Path

from . import music


def main(count):
    music.LIBRARY.mkdir(parents=True, exist_ok=True)
    failures = 0
    for i in range(1, count + 1):
        out = music.LIBRARY / f"track-{i:02d}.mp3.enc"
        if out.exists():
            print(f"[{i}] już jest, pomijam")
            continue
        style = music.STYLES[(i - 1) % len(music.STYLES)]
        try:
            with tempfile.TemporaryDirectory() as tmp:
                raw = Path(tmp) / "t.mp3"
                if not music.generate(raw, 19, style=style):
                    sys.exit("Brak ELEVENLABS_API_KEY.")
                music.encrypt_file(raw, out)
            print(f"[{i}] ok: {style}")
        except Exception as exc:  # jedna nieudana ścieżka nie przerywa reszty
            failures += 1
            print(f"[{i}] BŁĄD: {exc}", file=sys.stderr)
    print(f"Biblioteka: {len(music.library())} ścieżek, błędów: {failures}")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
