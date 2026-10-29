import os

import requests

API = "https://www.googleapis.com/youtube/v3"


def collect():
    key = os.getenv("YOUTUBE_API_KEY")
    channel_id = os.getenv("YOUTUBE_CHANNEL_ID")
    if not (key and channel_id):
        return None

    ch = requests.get(f"{API}/channels", params={
        "part": "statistics,contentDetails", "id": channel_id, "key": key,
    }, timeout=30).json()["items"][0]
    stats = ch["statistics"]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]

    items = requests.get(f"{API}/playlistItems", params={
        "part": "contentDetails", "playlistId": uploads, "maxResults": 10, "key": key,
    }, timeout=30).json().get("items", [])
    ids = ",".join(i["contentDetails"]["videoId"] for i in items)
    videos = []
    if ids:
        for v in requests.get(f"{API}/videos", params={
            "part": "snippet,statistics", "id": ids, "key": key,
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
