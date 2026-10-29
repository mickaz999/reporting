import os

import requests

from ._common import MAX_PAGES, parse_date, since

API = "https://www.googleapis.com/youtube/v3"


def collect():
    key = os.getenv("YOUTUBE_API_KEY")
    channel_id = os.getenv("YOUTUBE_CHANNEL_ID")
    if not (key and channel_id):
        return None

    # Accepte l'ID de chaîne (UC…) ou le pseudo (@mickaz9).
    lookup = {"forHandle": channel_id} if channel_id.startswith("@") else {"id": channel_id}
    ch = requests.get(f"{API}/channels", params={
        "part": "statistics,contentDetails", "key": key, **lookup,
    }, timeout=30).json()["items"][0]
    stats = ch["statistics"]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]

    # La playlist des uploads est triée de la plus récente à la plus ancienne.
    ids, page_token, limit = [], None, since()
    for _ in range(MAX_PAGES):
        r = requests.get(f"{API}/playlistItems", params={
            "part": "contentDetails", "playlistId": uploads, "maxResults": 50,
            "pageToken": page_token, "key": key,
        }, timeout=30).json()
        recent = [i for i in r.get("items", [])
                  if parse_date(i["contentDetails"].get("videoPublishedAt", "1970-01-01T00:00:00Z")) >= limit]
        ids += [i["contentDetails"]["videoId"] for i in recent]
        page_token = r.get("nextPageToken")
        if not page_token or len(recent) < len(r.get("items", [])):
            break

    videos = []
    for start in range(0, len(ids), 50):  # l'API accepte 50 ids par appel
        for v in requests.get(f"{API}/videos", params={
            "part": "snippet,statistics", "id": ",".join(ids[start:start + 50]), "key": key,
        }, timeout=30).json().get("items", []):
            s = v["statistics"]
            videos.append({
                "titre": v["snippet"]["title"],
                "date": v["snippet"]["publishedAt"],
                "vues": int(s.get("viewCount", 0)),
                "likes": int(s.get("likeCount", 0)),
                "commentaires": int(s.get("commentCount", 0)),
                "lien": f"https://youtu.be/{v['id']}",
            })

    return {
        "abonnes": int(stats.get("subscriberCount", 0)),
        "vues_totales": int(stats.get("viewCount", 0)),
        "nb_videos": int(stats.get("videoCount", 0)),
        "dernieres_publications": videos,
    }
