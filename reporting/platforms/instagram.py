import os

import requests

from ._common import MAX_PAGES, parse_date, since

def collect():
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    if not token:
        return None
    # Sans ID de compte : jeton « Instagram Login » (graph.instagram.com, pas besoin de Page Facebook)
    account = os.getenv("INSTAGRAM_ACCOUNT_ID")
    API = "https://graph.facebook.com/v21.0" if account else "https://graph.instagram.com/v21.0"
    account = account or "me"

    me = requests.get(f"{API}/{account}", params={
        "fields": "username,followers_count,media_count", "access_token": token,
    }, timeout=30).json()
    if "error" in me:
        raise RuntimeError(me["error"].get("message", me["error"]))
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
