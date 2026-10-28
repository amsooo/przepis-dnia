# Szybki odbiór kliknięć: webhook Telegrama przez Cloudflare Worker

Telegram → Worker (`index.js`) → GitHub `poll.yml` (z jedną akcją w środku). Reakcja w kilkanaście sekund zamiast do godziny.

## Konfiguracja (jednorazowo)
1. **Chat ID**: uruchom w Actions „Konfiguracja", krok `whoami` (przed włączeniem webhooka); bot odeśle Twoje chat_id na Telegramie.
2. **Token GitHub** (Settings → Developer settings → Fine-grained personal access tokens): tylko repo `przepis-dnia`,
   uprawnienie **Actions: Read and write**, najdłuższa ważność. Nic więcej.
3. **Cloudflare** (darmowe konto): Workers & Pages → Create → Worker `przepis-dnia-bot` → Edit code → wklej `worker/index.js` → Deploy.
   Settings → Variables and Secrets:
   - secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET` (dowolny losowy ciąg, np. 32 znaki), `GITHUB_TOKEN` (token z kroku 2)
   - zwykłe zmienne: `ALLOWED_CHAT_ID` (z kroku 1), `GITHUB_REPO` = `amsooo/przepis-dnia`
4. **Repo (Settings → Secrets and variables → Actions)**: secret `TELEGRAM_WEBHOOK_SECRET` (ten sam ciąg co w Workerze),
   zmienna `WORKER_URL` = adres Workera (`https://przepis-dnia-bot.<twoja-subdomena>.workers.dev`).
5. Actions → „Konfiguracja" → krok `webhook-on`. Potem `webhook-info` pokaże adres i ewentualny błąd.

## Jak działa i uwagi
- Worker sprawdza tajny nagłówek Telegrama i ignoruje wszystko spoza Twojego czatu; od razu potwierdza przycisk („Przyjęto, pracuję…").
- Gdy webhook jest włączony, harmonogram `poll.yml` nie pyta Telegrama (to niemożliwe), tylko pilnuje automatycznej publikacji.
- GitHub nie kolejkuje więcej niż jednego oczekującego uruchomienia na grupę: jeśli klikniesz kilka przycisków w ułamku sekundy,
  jedno może zostać pominięte. Poczekaj na odpowiedź bota i kliknij ponownie.
- Powrót do starego trybu: `webhook-off` (odbiór co kilkadziesiąt minut lub ręcznie).
- Token GitHub w Workerze wygasa (maks. rok): po wygaśnięciu kliknięcia przestaną dochodzić; wygeneruj nowy i podmień secret `GITHUB_TOKEN` w Workerze.
