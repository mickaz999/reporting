from datetime import datetime, timedelta, timezone

MAX_PAGES = 20  # garde-fou contre une boucle infinie


def since():
    return datetime.now(timezone.utc) - timedelta(days=7)


def parse_date(d):
    if isinstance(d, (int, float)):  # TikTok renvoie un timestamp Unix
        return datetime.fromtimestamp(d, timezone.utc)
    return datetime.fromisoformat(d.replace("Z", "+00:00").replace("+0000", "+00:00"))
