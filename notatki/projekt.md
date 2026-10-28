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
- Kolory: prompt prosi o żywe, nasycone barwy i kontrastowy talerz/tło, a po generowaniu `image.generate` podbija nasycenie (x1.25) i kontrast (x1.08).
- Zdjęcie jest przycinane do proporcji 4:5 (Instagram odrzuca węższe).

## Instagram
- Ścieżka: „Instagram API with Instagram login" (aplikacja Meta z przypadkiem użycia „Manage messaging & content on Instagram"),
  uprawnienie `instagram_business_content_publish` dodane w Permissions and features. Aplikacja zostaje w trybie Development (bez App Review),
  konto ma rolę Instagram Tester.
- Token generowany w panelu aplikacji (API setup with Instagram login → Generate token). Ważny ok. 60 dni, potem trzeba wygenerować nowy
  i podmienić secret `IG_ACCESS_TOKEN`. Przypomnienie: zmienna repo `IG_TOKEN_DATE` (RRRR-MM-DD, data wygenerowania tokenu); od 15 dni przed wygaśnięciem `propose` wysyła codziennie ostrzeżenie na Telegram (`src/reminders.py`). Po odnowieniu tokenu zaktualizuj zarówno secret `IG_ACCESS_TOKEN`, jak i `IG_TOKEN_DATE`.
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
- Stała godzina publikacji (np. 18:00) zamiast „po odbiorze kliknięcia"; automatyczna publikacja po upływie czasu.
- (zrobione i uruchomione) Szybszy odbiór kliknięć: `worker/` (Cloudflare Worker → `workflow_dispatch` z akcją w `UPDATE_JSON`), instrukcja w `worker/README.md`. Webhook włącza krok `webhook-on` w „Konfiguracja”.

## Decyzja o wizerunku konta (2026-10-28)
Odradzone: profil udający prawdziwą osobę (wygenerowana twarz, wymyślone bio „mama gotuje dla rodziny"): wprowadza w błąd, narusza zasady Meta
dot. oznaczania treści AI i autentyczności konta (ryzyko ograniczenia zasięgu/blokady), a w opisie posta jest uczciwy dopisek o zdjęciach AI.
Rekomendowane: wyraźnie fikcyjna maskotka (rysunkowa/ilustracyjna) i nazwa-marka, bez udawania człowieka.

## Wizerunek: ustalone (2026-10-28)
- Maskotka: rysunkowy, okrągły kucharz „Szef Wąsik" (wersja 2) na turkusowym tle (alternatywa: żółte). Pliki w `branding/`.
- Nazwa wyświetlana: „Przepisy dnia | Szef Wąsik" (26 znaków). `@przepisy_dnia` bez zmian (zmiana @ psuje linki).
- Opis (118–120 znaków, trzy warianty do wyboru): maskotka konta, codziennie nowy przepis, składniki na drugim slajdzie, zdjęcia z AI.
- Wgrywa właściciel ręcznie w aplikacji Instagram (API nie pozwala ustawić zdjęcia profilowego/nazwy).

## Odbiór kliknięć przez webhook (2026-10-28): URUCHOMIONY i przetestowany
Działa na produkcji: kliknięcie → „Przyjęto, pracuję…” od razu, nowy podgląd po kilkunastu sekundach do 2 min (ciężkie akcje: Inny przepis / Inne zdjęcie).
Kod: `worker/index.js`, `poll.yml` przyjmuje wejście `update`, `src/main.py` obsługuje pojedynczą akcję (deduplikacja po `last_update_id`)
i w trybie webhooka nie wywołuje getUpdates. Kroki konfiguracji: `worker/README.md`. Uwaga: GitHub kolejkuje max jedno oczekujące uruchomienie na grupę
`ig-bot`, więc przy kilku kliknięciach w ułamku sekundy jedno może zginąć (kliknąć ponownie).
- Konfiguracja produkcyjna: Worker `przepis-dnia-bot` na workers.dev; secrets w Workerze: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `GITHUB_TOKEN` (fine-grained PAT, tylko to repo, Actions: Read and write, wygasa: odnowić); zmienne: `ALLOWED_CHAT_ID`, `GITHUB_REPO`.
  W repo: secret `TELEGRAM_WEBHOOK_SECRET`, zmienna `WORKER_URL` (adres `.workers.dev`, NIE adres panelu Cloudflare).
- Powrót do trybu odpytywania: krok `webhook-off` w „Konfiguracja”. Nie klikać kolejnych przycisków, zanim bot odpowie na poprzednie.
