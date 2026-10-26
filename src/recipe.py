import json
import re
from datetime import date

from . import gemini

# Rotacja kategorii daje różnorodność bez ustalania niszy.
CATEGORIES = [
    "śniadanie lub brunch",
    "zupa",
    "obiad z mięsem lub rybą",
    "danie wegetariańskie lub wegańskie",
    "makaron, ryż lub kasza",
    "deser lub wypiek",
    "szybka przekąska lub kolacja",
]

SYSTEM = """Jesteś redaktorem popularnego polskiego konta kulinarnego na Instagramie.
Piszesz po polsku, ciepło i konkretnie, bez przesadnej egzaltacji.
Przepisy muszą być realne, wykonalne w domowej kuchni, z dokładnymi ilościami (g, ml, łyżki) i czasami.
Zwracasz WYŁĄCZNIE obiekt JSON, bez komentarza i bez bloku markdown."""

# Dopisywane do każdego promptu zdjęcia: modele obrazów psują sztućce i dokładają dodatkowe talerze.
IMAGE_RULES = ("Composition: exactly one plate or bowl with the finished dish, centered, on a plain simple surface. "
               "No cutlery, no forks or spoons, no additional plates, side dishes or other food items, no hands, no text. "
               "Realistic, physically correct objects.")

SCHEMA = """Format JSON:
{
  "title": "nazwa dania",
  "intro": "1-2 zdania zachęty",
  "time_min": liczba minut łącznie,
  "servings": liczba porcji,
  "ingredients": ["300 g ...", "..."],
  "steps": ["krok 1", "..."],
  "tip": "krótka wskazówka albo pusty napis",
  "hashtags": ["#przepis", "..."],  // 8-12 sztuk
  "image_prompt": "opis zdjęcia gotowego dania PO ANGIELSKU: realistyczna fotografia kulinarna, naturalne światło, ujęcie 45 stopni, jedno danie na jednym talerzu, bez sztućców, bez dodatków obok, bez ludzi i bez tekstu"
}"""


def _parse(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    data = json.loads(text)
    for key in ("title", "intro", "time_min", "servings", "ingredients", "steps", "hashtags", "image_prompt"):
        if key not in data:
            raise ValueError(f"Brak pola {key}")
    return data


def _ask(prompt, retries=2):
    last = None
    for _ in range(retries + 1):
        data = gemini.generate("text", "TEXT_MODEL", "gemini-2.5-flash", {
            "systemInstruction": {"parts": [{"text": SYSTEM}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 8000},
        })
        try:
            return _parse(data["candidates"][0]["content"]["parts"][0]["text"])
        except (KeyError, IndexError, ValueError) as exc:  # JSONDecodeError dziedziczy po ValueError
            last = exc
    raise RuntimeError(f"Gemini nie zwrócił poprawnego JSON-a: {last}")


def generate(recent_titles, today=None):
    today = today or date.today()
    category = CATEGORIES[today.toordinal() % len(CATEGORIES)]
    avoid = "; ".join(recent_titles[-60:]) or "brak"
    prompt = (
        f"Wymyśl jeden przepis na dziś. Kategoria: {category}. Kuchnia dowolna, może być polska lub światowa.\n"
        f"Nie powtarzaj tych dań ani ich bliskich wariantów: {avoid}.\n{SCHEMA}"
    )
    return _ask(prompt)


def revise(recipe, feedback):
    """Zwraca (nowy przepis, czy trzeba przegenerować zdjęcie)."""
    prompt = (
        "Oto aktualny przepis:\n"
        f"{json.dumps(recipe, ensure_ascii=False)}\n\n"
        f"Uwagi właściciela konta: {feedback}\n\n"
        "Wprowadź dokładnie te zmiany i zachowaj resztę. Jeśli uwagi dotyczą wyglądu dania lub zdjęcia, "
        "zmień też image_prompt. Dodaj pole \"regenerate_image\": true/false (true, gdy zmieniło się danie "
        f"albo wygląd zdjęcia).\n{SCHEMA}"
    )
    data = _ask(prompt)
    regenerate = bool(data.pop("regenerate_image", False))
    return data, regenerate


def build_caption(recipe, ai_disclosure=True):
    lines = [recipe["title"].upper(), "", recipe["intro"], ""]
    lines.append(f"⏱ {recipe['time_min']} min  |  🍽 porcje: {recipe['servings']}")
    lines += ["", "SKŁADNIKI:"] + [f"• {i}" for i in recipe["ingredients"]]
    lines += ["", "PRZYGOTOWANIE:"] + [f"{n}. {s}" for n, s in enumerate(recipe["steps"], 1)]
    if recipe.get("tip"):
        lines += ["", f"💡 {recipe['tip']}"]
    if ai_disclosure:
        lines += ["", "Zdjęcie wygenerowane przez AI."]
    tags = " ".join(recipe["hashtags"][:15])
    caption = "\n".join(lines) + "\n\n" + tags
    if len(caption) > 2200:  # limit Instagrama; ucinamy hashtagi, potem wskazówkę
        caption = "\n".join(lines) + "\n\n" + " ".join(recipe["hashtags"][:5])
    return caption[:2200]
