"""Reel 9:16 (ok. 12 s) ze zdjęcia dania i karty składników: powolne przybliżenie, tytuł i krótkie napisy, bez muzyki."""
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from .card import CREAM, FONTS, _wrap

W, H, FPS = 1080, 1920, 30
FADE = 12  # klatek płynnego przejścia między slajdami


def _ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg  # statyczny ffmpeg z pip, gdy w systemie go brak
    return imageio_ffmpeg.get_ffmpeg_exe()


def _font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def _background(photo):
    """Rozmyte, przyciemnione tło wypełniające kadr 9:16, na które trafia zdjęcie i napisy."""
    scale = max(W / photo.width, H / photo.height)
    big = photo.resize((round(photo.width * scale), round(photo.height * scale)), Image.BICUBIC)
    left, top = (big.width - W) // 2, (big.height - H) // 2
    bg = big.crop((left, top, left + W, top + H)).filter(ImageFilter.GaussianBlur(40))
    return ImageEnhance.Brightness(bg).enhance(0.42)


def _fit_title(draw, title, max_width, max_lines=3):
    for size in range(72, 40, -4):
        font = _font("DejaVuSerif-Bold.ttf", size)
        lines = _wrap(draw, title, font, max_width)
        if len(lines) <= max_lines:
            return font, lines
    return font, lines[:max_lines]


def _centered(draw, text, font, y, fill):
    draw.text(((W - draw.textlength(text, font=font)) / 2, y), text, font=font, fill=fill)


def _segment_a(photo, recipe):
    fg = photo.resize((W, round(W * photo.height / photo.width)), Image.BICUBIC)
    top = (H - fg.height) // 2
    bg = _background(photo)
    d = ImageDraw.Draw(bg)
    font, lines = _fit_title(d, recipe["title"], W - 140)
    step = int(font.size * 1.18)
    y = (top - len(lines) * step) // 2 + 10
    for line in lines:
        _centered(d, line, font, y, (255, 255, 255))
        y += step
    base_y = top + fg.height
    room = H - base_y
    _centered(d, f"{recipe['time_min']} min   •   porcje: {recipe['servings']}", _font("DejaVuSans-Bold.ttf", 46),
              base_y + room * 0.18, (255, 205, 130))
    _centered(d, "Składniki za chwilę", _font("DejaVuSans.ttf", 40), base_y + room * 0.43, (255, 255, 255))
    _centered(d, "@przepisy_dnia", _font("DejaVuSans-Bold.ttf", 38), base_y + room * 0.66, (255, 205, 130))
    return fg, bg, top


def _segment_b(card_img):
    bg = Image.new("RGB", (W, H), CREAM)
    top = (H - card_img.height) // 2
    bg.paste(card_img, (0, top))
    return bg


def render(photo_path, card_path, recipe, out_path, seconds_a=5.0):
    photo = Image.open(photo_path).convert("RGB")
    card_img = Image.open(card_path).convert("RGB")
    fg, bg_a, top = _segment_a(photo, recipe)
    frame_b = _segment_b(card_img)
    n_a = int(seconds_a * FPS)
    n_b = int(min(9.0, 4.0 + 0.4 * len(recipe["ingredients"])) * FPS)

    cmd = [_ffmpeg(), "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100", "-shortest",
           "-c:v", "libx264", "-preset", "medium", "-crf", "27", "-pix_fmt", "yuv420p", "-r", str(FPS),
           "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(out_path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        last_a = None
        for i in range(n_a):
            t = i / (n_a - 1)
            s = 1.0 + 0.09 * (t * t * (3 - 2 * t))          # łagodne przyspieszenie i zwolnienie
            size = (round(fg.width * s), round(fg.height * s))
            zoomed = fg.resize(size, Image.BICUBIC)
            left, upper = (size[0] - fg.width) // 2, (size[1] - fg.height) // 2
            frame = bg_a.copy()
            frame.paste(zoomed.crop((left, upper, left + fg.width, upper + fg.height)), (0, top))
            proc.stdin.write(frame.tobytes())
            last_a = frame
        for k in range(FADE):                                # przejście do karty składników
            proc.stdin.write(Image.blend(last_a, frame_b, (k + 1) / (FADE + 1)).tobytes())
        data_b = frame_b.tobytes()
        for _ in range(n_b):
            proc.stdin.write(data_b)
        proc.stdin.close()
        err = proc.stderr.read().decode()[-300:]
        if proc.wait() != 0:
            raise RuntimeError(f"ffmpeg zakończył się błędem: {err}")
    except BrokenPipeError:
        raise RuntimeError(f"ffmpeg przerwał pracę: {proc.stderr.read().decode()[-300:]}")
    finally:
        if proc.poll() is None:
            proc.kill()
