import os

import requests

from ._common import MAX_PAGES, parse_date, since

API = "https://api.twitch.tv/helix"


def collect():
    client_id = os.getenv("TWITCH_CLIENT_ID")
    secret = os.getenv("TWITCH_CLIENT_SECRET")
    login = os.getenv("TWITCH_LOGIN")
    if not (client_id and secret and login):
        return None

    token = requests.post("https://id.twitch.tv/oauth2/token", params={
        "client_id": client_id, "client_secret": secret, "grant_type": "client_credentials",
    }, timeout=30).json()["access_token"]
    h = {"Client-Id": client_id, "Authorization": f"Bearer {token}"}

    user = requests.get(f"{API}/users", params={"login": login}, headers=h, timeout=30).json()["data"][0]
    uid = user["id"]
    # Avec un token d'application, l'API ne renvoie que le total des followers.
    followers = requests.get(f"{API}/channels/followers", params={"broadcaster_id": uid},
                             headers=h, timeout=30).json().get("total", 0)
    live = requests.get(f"{API}/streams", params={"user_id": uid}, headers=h, timeout=30).json()["data"]
    vods, cursor, limit = [], None, since()
    for _ in range(MAX_PAGES):
        r = requests.get(f"{API}/videos", params={"user_id": uid, "type": "archive", "first": 100,
                                                  "after": cursor}, headers=h, timeout=30).json()
        page = r.get("data", [])
        recent = [v for v in page if parse_date(v["created_at"]) >= limit]
        vods += recent
        cursor = r.get("pagination", {}).get("cursor")
        if not cursor or len(recent) < len(page):
            break

    return {
        "followers": followers,
        "en_live": bool(live),
        "spectateurs_actuels": live[0]["viewer_count"] if live else 0,
        "dernieres_publications": [{
            "titre": v["title"],
            "date": v["created_at"],
            "vues": v["view_count"],
            "duree": v["duration"],
            "lien": v["url"],
        } for v in vods],
    }
