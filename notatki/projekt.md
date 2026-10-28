# Przepis dnia — ustalenia i stan prac

Cel: konto kulinarne @przepisy_dnia na Instagramie, jeden przepis dziennie ze zdjęciem gotowego dania,
niemal pełna automatyzacja z akceptacją przez Telegram.

## Stan (2026-10-26)
Działa od początku do końca: przepis → zdjęcie → podgląd na Telegramie → Akceptuj → publikacja na IG.
Pierwszy post opublikowany. Logo i opis profilu ustawia właściciel ręcznie w aplikacji Instagram.

## Jak to działa
- `propose.yml` (cron 06:00 UTC, w praktyce 06:15–06:25): Gemini pisze przepis, generator robi zdjęcie,
  na Telegram idzie podgląd z przyciskami Akceptuj / Popraw / Inny przepis / Inne zdjęcie.
- `poll.yml` (cron */5, w praktyce co 45–60 min; można odpalić ręcznie): odbiera kliknięcia i uwagi,
  poprawia przepis, regeneruje zdjęcie albo publikuje na Instagramie.
- Stan w repo: `state.json` (oczekujący przepis + offset Telegrama), `history.json`, `media/` (zdjęcia).
- Bez reakcji post czeka, a kolejnego przepisu nie generujemy. `AUTO_PUBLISH_AFTER_HOURS=N` publikuje sam po N godzinach (domyślnie wyłączone).
- Bot reaguje tylko na jeden czat (`TELEGRAM_CHAT_ID`). Błąd pojedynczej akcji idzie na Telegram jako ostrzeżenie i nie blokuje kolejki.
- Workflow pomocnicze: `setup.yml` (kroki `whoami`, `check`, `models`), `ig-setup.yml` (tylko dla ścieżki z logowaniem przez Facebooka).

## Karuzela i hashtagi (od 2026-10-28)
- Post to karuzela 2 slajdów: (1) zdjęcie dania, (2) karta ze składnikami rysowana lokalnie w Pillow (`src/card.py`, czcionki DejaVu w `assets/fonts/`),
  żeby polskie litery były zawsze poprawne. Karta powstaje na nowo przy każdej zmianie przepisu. Przepisy sprzed karuzeli publikują się jako pojedyncze zdjęcie.
- Hashtagi składa kod (`finalize_hashtags` w `src/recipe.py`): 3 popularne polskie tagi kulinarne rotowane dniami + 2 tagi kategorii dania + 2 tagi specyficzne od modelu
  (bez polskich znaków). Razem do 7. Pula `BROAD_TAGS` pochodzi z zestawień popularnych polskich tagów (liczb postów nie udało się zweryfikować).

## Dostawcy
- Tekst: Gemini API (klucz z AI Studio). Model wybierany automatycznie z listy dostępnej dla klucza
  (najnowszy stabilny „flash"), ponawianie przy 5xx, timeout 90 s, potem kolejny model. Wymuś zmienną `TEXT_MODEL`.
- Zdjęcia, łańcuch `IMAGE_PROVIDERS` (domyślnie `magnific,gemini,pollinations`; dostawca bez klucza jest pomijany):
  1. Magnific, model `seedream-v5-pro` (`MAGNIFIC_MODEL`; `classic` = stary endpoint). Zadania asynchroniczne. Ok. 50–60 kredytów za zdjęcie.
  2. Gemini: API NIE ma darmowego limitu na obrazy (429), działa tylko po włączeniu płatności.
  3. Pollinations: darmowy, ale słaby i ze znakiem wodnym. Pod zdjęciem z rezerwy bot dopisuje ostrzeżenie.
- Do każdego promptu zdjęcia dopisywane są reguły realizmu i kompozycji (`IMAGE_RULES` w `src/recipe.py`): jedna porcja, ścisły kadr,
  bez wzmianki o sztućcach (modele rysują to, co się wymieni).
- Zdjęcie jest przycinane do proporcji 4:5 (Instagram odrzuca węższe).

## Instagram
- Ścieżka: „Instagram API with Instagram login" (aplikacja Meta z przypadkiem użycia „Manage messaging & content on Instagram"),
  uprawnienie `instagram_business_content_publish` dodane w Permissions and features. Aplikacja zostaje w trybie Development (bez App Review),
  konto ma rolę Instagram Tester.
- Token generowany w panelu aplikacji (API setup with Instagram login → Generate token). Ważny ok. 60 dni, potem trzeba wygenerować nowy
  i podmienić secret `IG_ACCESS_TOKEN`. Brak jeszcze automatycznego przypomnienia.
- Host API wybierany po prefiksie tokenu (`IG...` → graph.instagram.com, `EAA...` → graph.facebook.com); `IG_GRAPH_HOST` jest opcjonalne.
- **Repo musi być publiczne**: Instagram pobiera zdjęcie z raw.githubusercontent.com, w prywatnym repo dostaje 404 (publikacja kończy się 400).
- Secrets: `GEMINI_API_KEY`, `MAGNIFIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `IG_USER_ID`, `IG_ACCESS_TOKEN`. Nic z tego nie leży w repo.

## Pułapki (nauczone na własnej skórze)
- Cron GitHuba bywa opóźniony o kilkadziesiąt minut. Po kliknięciu na Telegramie odpal ręcznie „Odbiór decyzji z Telegrama" i NIE anuluj uruchomienia,
  bo anulowanie gubi kliknięcie (offset nie zostaje zapisany).
- Telegram przyjmuje odpowiedź na kliknięcie tylko przez chwilę; przy opóźnionym odbiorze 400 jest normalne (ignorowane).
- `actions/checkout` bierze SHA z momentu wyzwolenia, więc workflow używa `ref: main` i `git pull --rebase` przed push (kolizje z commitami bota).
- Kolejność: najpierw kliknięcie na Telegramie, potem uruchomienie odbioru.
- Zdjęcia z AI: w opisie jest dopisek; etykietę „Informacje o AI" właściciel włącza ręcznie w poście.
- Panel Meta: tworzenie konta developera na nowym urządzeniu bywa blokowane („You can't make this change at the moment"); przejść z zaufanego urządzenia.

## Pomysły na później
- Przypomnienie na Telegramie o odnowieniu tokenu IG (ok. 50 dni).
- Stała godzina publikacji (np. 18:00) zamiast „po odbiorze kliknięcia"; automatyczna publikacja po upływie czasu.
- Szybszy odbiór kliknięć: webhook Telegrama przez Cloudflare Worker + `repository_dispatch`.
