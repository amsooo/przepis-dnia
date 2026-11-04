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

## Awaria generowania przepisu (2026-11-01)
Gemini bywa przeciążony (503 / brak odpowiedzi na wszystkich modelach naraz); wcześniej bot milczał. Teraz: dłuższe odstępy ponowień i do 4 modeli w łańcuchu,
powiadomienie na Telegramie o błędzie oraz ponowne próby z harmonogramu o 09:00 i 12:00 UTC (strażnik `last_proposed` w `state.json` robi z nich ciche no-opy,
jeśli przepis już był; ręczne uruchomienie „Codzienny przepis” zawsze generuje).

## Reel, hak w opisie, mniej hashtagów (2026-11-03)
Powód: 10 postów bez wyświetleń (status konta w porządku, profil publiczny): problem w dystrybucji, nie w blokadzie.
- Reel 9:16 (ok. 14 s, ok. 0,8 MB, `src/reel.py`): zdjęcie z powolnym przybliżeniem na rozmytym tle, tytuł, czas i porcje, potem karta składników; bez muzyki.
  Montaż ffmpeg (systemowy albo `imageio-ffmpeg` z pip). Powstaje po każdej zmianie zdjęcia/karty; awaria filmu nie blokuje karuzeli.
- Publikacja: zmienna repo `POST_FORMAT` = `both` (domyślnie: karuzela + reel), `reel` albo `carousel`. Postęp zapisywany w `pending.published`,
  więc po awarii w połowie ponowny Akceptuj nie dubluje już opublikowanych formatów.
- Opis: pierwsza linia to „hak” od modelu (`hook`, ze słowami kluczowymi), na końcu „Zapisz ten przepis na później”.
- Hashtagi: 5 (1 popularny rotowany + 2 kategorii + 2 specyficzne dla dania).
- Nieprzetestowane na prawdziwym Instagramie (publish_reel): pierwszą publikację sprawdzić; w razie błędu ustawić `POST_FORMAT=carousel`.
- Uwaga: Reel dokłada plik mp4 do repo przy każdym przepisie (rośnie historia git); w razie potrzeby czyścić stare media/.

## Muzyka do Reela (2026-11-03)
- Muzyka z biblioteki Instagrama niedostępna przez API (wybiera się ją tylko ręcznie w aplikacji).
- Biblioteka ok. 10 instrumentalnych ścieżek (po ok. 19 s) z ElevenLabs (Eleven Music, `POST /v1/music`) generowana JEDEN raz workflow „Muzyka – wygeneruj
  bibliotekę podkładów” (`src/make_music.py`, 10 różnych klimatów w `src/music.py`; istniejące pliki są pomijane, więc ponowne uruchomienie dokańcza brakujące).
- Repo jest publiczne, a warunków ElevenLabs co do udostępniania samodzielnych plików nie zweryfikowano, więc ścieżki leżą w `assets/music/*.mp3.enc`
  ZASZYFROWANE (Fernet, klucz z PBKDF2 z sekretu `MUSIC_KEY`; gdy go brak, z `TELEGRAM_WEBHOOK_SECRET`). UWAGA: zmiana tego sekretu = nie do odszyfrowania,
  trzeba usunąć pliki i wygenerować bibliotekę od nowa (koszt kredytów).
- Przy renderze filmu bot odszyfrowuje jedną ścieżkę do katalogu tymczasowego: kolejność rotuje wg liczby dotychczasowych publikacji (`len(history)`),
  miksuje (zapętlenie, wejście 0,8 s, wyciszenie 1,5 s, głośność 0,8). Render nie zużywa już limitu ElevenLabs.
- Brak biblioteki / zły klucz = cichy film (ostrzeżenie na Telegramie); wyłączenie muzyki: zmienna repo `REEL_MUSIC=0`.
- Plan ElevenLabs właściciela obejmuje muzykę; warunki komercyjne sprawdzić w Eleven Music Terms. Próbka bez przepisu: „Konfiguracja” → `music-test`.

## Gemini: łańcuch modeli (2026-11-03)
Najnowsze modele „flash” bywają przeciążone godzinami (503 na wszystkich naraz). Łańcuch tekstu ma teraz do 8 modeli: stabilne nie-lite od najnowszego, potem testowe,
na końcu warianty „lite”; po 2 próby na model (przerwy 8 i 20 s), przy timeoucie od razu następny. Zdjęcia: do 3 modeli bez lite.

## Zapas przepisów (2026-11-04)
Gemini bywał przeciążony na wszystkich modelach przez wiele godzin (2 nieudane poranne próby tego samego dnia). Dlatego `state.json` ma kolejkę `queue`
(do 5 gotowych przepisów, generowanych z datami z przyszłości dla różnorodności kategorii). `propose` i „Inny przepis” biorą przepis z początku zapasu
(natychmiast, bez Gemini); dopiero gdy zapas jest pusty, generują nowy. Po każdym udanym `propose` zapas jest uzupełniany (do 3 szt., pierwszy błąd przerywa),
a nocny workflow „Zapas przepisów” (02:17 UTC, `python -m src.main refill`) dobija do pełna. Przy małym zapasie bot pisze na Telegramie.
Wady: przepis z zapasu może mieć kilka dni; jeśli Gemini nie działa dłużej niż zapas wystarcza, wracamy do błędu jak dawniej.

## Awaria zapisu stanu (2026-11-04)
Przepis dotarł na Telegram, ale `git push` dostał „remote: Internal Server Error” (chwilowa awaria GitHuba), więc `pending` nie trafił do repo i bot odpowiadał
„Nie ma niczego do zatwierdzenia”. Dodatkowo uzupełnianie zapasu opóźniało zapis stanu o ok. 10 min. Poprawki: zapis stanu z ponawianiem (5 prób, rosnące przerwy)
we wszystkich workflow'ach; uzupełnianie zapasu to osobny, późniejszy krok `propose.yml` (`continue-on-error`), a `refill` ma budżet 100 s na wywołanie Gemini.
Objaw „Nie ma niczego do zatwierdzenia” mimo przepisu na Telegramie = stan niezapisany: sprawdzić ostatni run `propose.yml`.
