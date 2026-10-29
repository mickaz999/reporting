import os

import requests

from ._common import MAX_PAGES, parse_date, since

API = "https://graph.facebook.com/v21.0"


def collect():
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    account = os.getenv("INSTAGRAM_ACCOUNT_ID")
    if not (token and account):
        return None

    me = requests.get(f"{API}/{account}", params={
        "fields": "username,followers_count,media_count", "access_token": token,
    }, timeout=30).json()
    media, limit = [], since()
    url, params = f"{API}/{account}/media", {
        "fields": "caption,timestamp,like_count,comments_count,permalink,media_type",
        "limit": 50, "access_token": token,
    }
    for _ in range(MAX_PAGES):
        r = requests.get(url, params=params, timeout=30).json()
        page = r.get("data", [])
        recent = [m for m in page if parse_date(m["timestamp"]) >= limit]
        media += recent
        # Le lien "next" contient déjà tous les paramètres.
        url, params = r.get("paging", {}).get("next"), None
        if not url or len(recent) < len(page):
            break

    return {
        "abonnes": me.get("followers_count", 0),
        "nb_publications": me.get("media_count", 0),
        "dernieres_publications": [{
            "titre": (m.get("caption") or "")[:80],
            "type": m.get("media_type"),
            "date": m.get("timestamp"),
            "likes": m.get("like_count", 0),
            "commentaires": m.get("comments_count", 0),
            "lien": m.get("permalink"),
        } for m in media],
    }
