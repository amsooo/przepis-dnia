// Cloudflare Worker: odbiera webhook Telegrama i uruchamia workflow "Odbiór decyzji" w GitHubie.
// Zmienne/sekrety Workera: TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET, GITHUB_TOKEN, ALLOWED_CHAT_ID, GITHUB_REPO.

export default {
  async fetch(request, env) {
    if (request.method !== "POST") return new Response("ok");
    if (request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.TELEGRAM_WEBHOOK_SECRET) {
      return new Response("forbidden", { status: 403 });
    }

    const update = await request.json();
    const cb = update.callback_query;
    const fromId = cb ? cb.from && cb.from.id : update.message && update.message.chat && update.message.chat.id;
    if (String(fromId) !== String(env.ALLOWED_CHAT_ID)) return new Response("ok"); // obcy: ignorujemy

    const jobs = [
      fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/poll.yml/dispatches`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github+json",
          "User-Agent": "przepis-dnia-worker",
          "X-GitHub-Api-Version": "2022-11-28",
          "content-type": "application/json",
        },
        body: JSON.stringify({ ref: "main", inputs: { update: JSON.stringify(update) } }),
      }),
    ];
    if (cb) {
      // potwierdzenie przycisku musi pójść w ciągu kilku sekund, dlatego robi je Worker, a nie GitHub
      jobs.push(fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/answerCallbackQuery`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ callback_query_id: cb.id, text: "Przyjęto, pracuję…" }),
      }));
    }
    const [dispatch] = await Promise.all(jobs);
    // przy błędzie GitHuba odpowiadamy 502, żeby Telegram ponowił dostarczenie (duplikaty odfiltruje bot po update_id)
    return new Response(dispatch.ok ? "ok" : "dispatch failed", { status: dispatch.ok ? 200 : 502 });
  },
};
