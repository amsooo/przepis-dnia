# Przepis dnia — automatyczne konto kulinarne na Instagramie

Codziennie rano bot wymyśla przepis, generuje zdjęcie dania i wysyła podgląd na Telegram.
Po kliknięciu **Akceptuj** publikuje na Instagramie. **Popraw** = wpisujesz uwagi, bot poprawia i znowu pyta.
**Inny przepis** = losuje nowy.

```
propose.yml (cron 1x dziennie) → Gemini (przepis) → obraz (Gemini → Pollinations → opcjonalnie OpenAI) → Telegram z przyciskami
poll.yml (co 5 min)            → odbiera klik / uwagi → poprawia | publikuje przez Instagram Graph API
```

Stan (`state.json`), historia (`history.json`) i zdjęcia (`media/`) są commitowane do repo.

## Wymagania: repo musi być PUBLICZNE
Instagram pobiera zdjęcie z publicznego adresu (`raw.githubusercontent.com`), a Actions są wtedy bez limitu minut.
W repo nie ma sekretów — wszystkie klucze siedzą w *Settings → Secrets and variables → Actions*.

## Konfiguracja (jednorazowo)
1. **Instagram**: konto biznesowe/twórcy połączone ze stroną na Facebooku. W Meta for Developers utwórz aplikację,
   dodaj uprawnienia `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`.
   Z długoterminowego tokenu użytkownika weź token strony (nie wygasa) i `IG_USER_ID` (id konta IG).
2. **Telegram**: bot z @BotFather → secret `TELEGRAM_BOT_TOKEN`. Napisz do bota „cześć”, uruchom workflow „Konfiguracja”
   (krok `whoami`) — bot odpisze Ci `chat_id` → secret `TELEGRAM_CHAT_ID`. Krok `check` sprawdza brakujące sekrety.
   Bot reaguje wyłącznie na ten jeden czat.
3. Klucz `GEMINI_API_KEY` z aistudio.google.com (tekst przepisów mieści się w darmowym limicie). Zdjęcia przez API Gemini
   zwykle wymagają płatnego konta, dlatego `IMAGE_PROVIDERS` (domyślnie `gemini,pollinations`) próbuje dostawców po kolei.
   Opcjonalnie `OPENAI_API_KEY` i `IMAGE_PROVIDERS=gemini,pollinations,openai`.
4. Secrets w repo: `GEMINI_API_KEY`, (opcjonalnie `OPENAI_API_KEY`), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `IG_USER_ID`, `IG_ACCESS_TOKEN`.
   Zmienne opcjonalne (jako env w workflow): `TEXT_MODEL`, `IMAGE_MODEL`, `IMAGE_PROVIDERS`, `AUTO_PUBLISH_AFTER_HOURS`.
5. Uruchom ręcznie workflow „Codzienny przepis” (Actions → Run workflow) i sprawdź Telegram.

## Zachowanie bez reakcji
Domyślnie post czeka na Twoją decyzję (a następnego dnia bot nie generuje nowego). Ustaw `AUTO_PUBLISH_AFTER_HOURS=N`,
żeby niezatwierdzony przepis opublikował się sam po N godzinach.

## Uwagi
- Zdjęcia są z AI; do opisu dopisywana jest informacja „Zdjęcie wygenerowane przez AI”. Włącz też etykietę AI w aplikacji IG.
- Testy: `pip install -r requirements.txt && pytest`.
- Cron GitHuba bywa opóźniony o kilka minut, więc reakcja na klik może trwać do ~10 min.
