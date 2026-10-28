from datetime import date

TOKEN_DAYS = 60       # ważność tokenu z panelu aplikacji Meta
REMIND_FROM = 15      # od ilu dni przed wygaśnięciem przypominamy (codziennie)

RENEW = ("Jak odnowić: developers.facebook.com → Twoja aplikacja → Przypadki użycia → Customize → "
         "API setup with Instagram login → przy koncie Generate token. Potem w repo podmień secret "
         "IG_ACCESS_TOKEN i ustaw zmienną IG_TOKEN_DATE na dzisiejszą datę (RRRR-MM-DD).")


def token_notice(token_date, today=None):
    """Tekst przypomnienia o tokenie Instagrama albo None, gdy jeszcze nie pora (lub brak daty)."""
    if not token_date:
        return None
    today = today or date.today()
    try:
        age = (today - date.fromisoformat(token_date.strip())).days
    except ValueError:
        return f"⚠️ IG_TOKEN_DATE ma zły format ({token_date!r}); oczekuję RRRR-MM-DD."
    left = TOKEN_DAYS - age
    if left < 0:
        return f"❌ Token Instagrama prawdopodobnie już wygasł ({-left} dni temu), publikacja nie zadziała.\n{RENEW}"
    if left <= REMIND_FROM:
        return f"⏰ Token Instagrama wygasa za około {left} dni.\n{RENEW}"
    return None
