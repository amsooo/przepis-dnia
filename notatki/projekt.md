# Przepis dnia — ustalenia

Cel: konto kulinarne na Instagramie, jeden przepis dziennie ze zdjęciem gotowego dania, pełna automatyzacja
z opcjonalną akceptacją przez Telegram.

## Decyzje
- Format: jedno zdjęcie + cały przepis w opisie (bez karuzeli i Reels). Kuchnia mieszana, bez niszy;
  różnorodność daje rotacja kategorii (`CATEGORIES` w `src/recipe.py`) i historia w `history.json`.
- Akceptacja: Telegram, przyciski Akceptuj / Popraw / Inny przepis. „Popraw" = bot prosi o uwagi,
  poprawia przepis (zdjęcie tylko gdy uwagi go dotyczą) i znowu pyta o akceptację, do skutku.
- Bez reakcji post czeka. Opcjonalnie `AUTO_PUBLISH_AFTER_HOURS=N` publikuje sam po N godzinach.
- Hosting: GitHub Actions, repo PUBLICZNE (Instagram pobiera zdjęcie z raw.githubusercontent.com,
  w prywatnym repo skończyłyby się darmowe minuty przy odpytywaniu Telegrama co 5 min). Sekrety tylko w Actions secrets.
- Make.com odrzucony: nadal potrzebuje API modelu, a pętla poprawek jest tam trudna.
- Koszty: tekst przez Gemini (darmowy limit). Zdjęcia: API Gemini zwykle NIE ma darmowego limitu na obrazy
  (limit „kilku dziennie" dotyczy aplikacji/AI Studio), stąd łańcuch `IMAGE_PROVIDERS`: gemini → pollinations → openai.
  Klucz Anthropic niepotrzebny (subskrypcja Claude nie daje klucza API).

## Stan prac (2026-10-24)
- Kod i testy gotowe (6 testów z atrapami), NIE uruchamiany na prawdziwych kontach.
- Nazwy modeli Gemini (`gemini-2.5-flash`, `gemini-2.5-flash-image`) niesprawdzone; zmienne `TEXT_MODEL`, `IMAGE_MODEL`.
- Do zrobienia przez właściciela: konto IG biznesowe + strona FB, aplikacja Meta (token strony, `IG_USER_ID`),
  bot Telegram, klucz Gemini, secrets w repo, ręczne odpalenie workflow „Codzienny przepis".

## Pułapki
- Zdjęcia muszą mieć proporcje między 4:5 a 1.91:1, inaczej API Instagrama odrzuca (kod przycina do 4:5).
- Zdjęcia z AI: w opisie jest dopisek, warto włączyć też etykietę AI w aplikacji IG.
- Cron GitHuba bywa opóźniony, reakcja na klik do ~10 min.
