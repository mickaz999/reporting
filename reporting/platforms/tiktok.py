import os

import requests

from ._common import MAX_PAGES, since

API = "https://open.tiktokapis.com/v2"


def _access_token():
    # Le token TikTok expire au bout de 24 h : on le régénère à chaque exécution.
    r = requests.post(f"{API}/oauth/token/", data={
        "client_key": os.environ["TIKTOK_CLIENT_KEY"],
        "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
        "grant_type": "refresh_token",
        "refresh_token": os.environ["TIKTOK_REFRESH_TOKEN"],
    }, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def collect():
    if not all(os.getenv(k) for k in ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN")):
        return None

    h = {"Authorization": f"Bearer {_access_token()}"}
    user = requests.get(f"{API}/user/info/", params={
        "fields": "display_name,follower_count,following_count,likes_count,video_count",
    }, headers=h, timeout=30).json()["data"]["user"]
    videos, cursor, limit = [], None, since().timestamp()
    for _ in range(MAX_PAGES):
        body = {"max_count": 20}
        if cursor:
            body["cursor"] = cursor
        r = requests.post(f"{API}/video/list/", params={
            "fields": "title,create_time,view_count,like_count,comment_count,share_count,share_url",
        }, json=body, headers=h, timeout=30).json().get("data", {})
        page = r.get("videos", [])
        recent = [v for v in page if v.get("create_time", 0) >= limit]
        videos += recent
        cursor = r.get("cursor")
        if not r.get("has_more") or len(recent) < len(page):
            break

    return {
        "abonnes": user.get("follower_count", 0),
        "likes_totaux": user.get("likes_count", 0),
        "nb_videos": user.get("video_count", 0),
        "dernieres_publications": [{
            "titre": v.get("title", ""),
            "date": v.get("create_time"),
            "vues": v.get("view_count", 0),
            "likes": v.get("like_count", 0),
            "commentaires": v.get("comment_count", 0),
            "partages": v.get("share_count", 0),
            "lien": v.get("share_url"),
        } for v in videos],
    }
