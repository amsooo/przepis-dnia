"""Slajd 2 karuzeli: karta ze składnikami (rysowana lokalnie, żeby polskie litery były zawsze poprawne)."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
W, H = 1080, 1350  # 4:5, tak samo jak zdjęcie na slajdzie 1
CREAM, TERRACOTTA, BROWN, SOFT = (251, 243, 228), (200, 98, 52), (74, 46, 32), (214, 196, 170)


def _font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def _wrap(draw, text, font, max_width):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def render(recipe, out_path, handle="@przepisy_dnia"):
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)
    margin = 90
    width = W - 2 * margin

    d.text((margin, 80), "SKŁADNIKI", font=_font("DejaVuSans-Bold.ttf", 34), fill=TERRACOTTA)
    y = 135
    title_font = _font("DejaVuSerif-Bold.ttf", 52)
    for line in _wrap(d, recipe["title"], title_font, width)[:3]:
        d.text((margin, y), line, font=title_font, fill=BROWN)
        y += 66
    meta = f"{recipe['time_min']} min   •   porcje: {recipe['servings']}"
    d.text((margin, y + 6), meta, font=_font("DejaVuSans.ttf", 30), fill=TERRACOTTA)
    y += 70
    d.line([(margin, y), (W - margin, y)], fill=SOFT, width=3)
    y += 35

    footer_y = H - 110
    bottom = footer_y - 30
    # największa czcionka, przy której cała lista mieści się w dostępnym miejscu
    items = list(recipe["ingredients"])
    while True:
        for size in range(44, 21, -2):
            font = _font("DejaVuSans.ttf", size)
            step = int(size * 1.35)
            gap = int(size * 0.55)
            item_width = width - 50
            layout = [_wrap(d, item, font, item_width) for item in items]
            total = sum(len(lines) * step + gap for lines in layout)
            if y + total <= bottom:
                break
        if y + total <= bottom or len(items) <= 3:
            break
        # nawet najmniejsza czcionka się nie mieści: ucinamy końcówkę i odsyłamy do opisu
        items = items[:-2] + ["… pozostałe składniki w opisie posta"]
    for lines in layout:
        d.ellipse([margin, y + step // 2 - 8, margin + 16, y + step // 2 + 8], fill=TERRACOTTA)
        for line in lines:
            d.text((margin + 50, y), line, font=font, fill=BROWN)
            y += step
        y += gap

    d.line([(margin, footer_y), (W - margin, footer_y)], fill=SOFT, width=3)
    small = _font("DejaVuSans-Bold.ttf", 30)
    d.text((margin, footer_y + 30), handle, font=small, fill=TERRACOTTA)
    note = "Cały przepis w opisie posta"
    d.text((W - margin - d.textlength(note, font=_font("DejaVuSans.ttf", 28)), footer_y + 32), note,
           font=_font("DejaVuSans.ttf", 28), fill=BROWN)
    img.save(out_path, "JPEG", quality=90)
