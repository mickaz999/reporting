import os
from datetime import datetime, timezone

import requests

from ._common import MAX_PAGES, parse_date, since

def collect():
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    if not token:
        return None
    # Jeton Instagram (« IG… ») : graph.instagram.com sur « me » ; jeton Facebook (« EAA… ») : graph.facebook.com + ID du compte
    if token.startswith("IG") or not os.getenv("INSTAGRAM_ACCOUNT_ID"):
        API, account = "https://graph.instagram.com/v21.0", "me"
    else:
        API, account = "https://graph.facebook.com/v21.0", os.environ["INSTAGRAM_ACCOUNT_ID"]

    me = requests.get(f"{API}/{account}", params={
        "fields": "username,followers_count,media_count", "access_token": token,
    }, timeout=30).json()
    if "error" in me:
        raise RuntimeError(me["error"].get("message", me["error"]))
    media, limit = [], since()
    url, params = f"{API}/{account}/media", {
        "fields": "id,caption,timestamp,like_count,comments_count,permalink,media_type,media_product_type",
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
        **_account_insights(API, account, token),
        "abonnes": me.get("followers_count", 0),
        "nb_publications": me.get("media_count", 0),
        "dernieres_publications": [{
            "titre": (m.get("caption") or "")[:80],
            "type": m.get("media_type"),
            "date": m.get("timestamp"),
            "likes": m.get("like_count", 0),
            "commentaires": m.get("comments_count", 0),
            "lien": m.get("permalink"),
            **_media_insights(API, m, token),
        } for m in media],
    }


# Statistiques détaillées : demandent l'autorisation « insights » sur l'app Meta ; ignorées sinon
def _insights(url, token, **params):
    r = requests.get(url, params={"access_token": token, **params}, timeout=30).json()
    if "error" in r:
        return None
    return {i["name"]: (i.get("total_value") or i.get("values", [{}])[-1]).get("value") for i in r.get("data", [])}


def _media_insights(api, m, token):
    reel = m.get("media_product_type") == "REELS"
    metrics = "reach,views,saved,shares" + (",ig_reels_avg_watch_time" if reel else "")
    data = _insights(f"{api}/{m['id']}/insights", token, metric=metrics) if m.get("id") else None
    if not data:
        return {}
    out = {"portee": data.get("reach"), "vues": data.get("views"), "enregistrements": data.get("saved"), "partages": data.get("shares")}
    if data.get("ig_reels_avg_watch_time"):
        out["temps_moyen_s"] = round(data["ig_reels_avg_watch_time"] / 1000, 1)
    return out


def _account_insights(api, account, token):
    data = _insights(f"{api}/{account}/insights", token, metric="reach,profile_views,website_clicks,accounts_engaged",
                     period="day", metric_type="total_value", since=int(since().timestamp()),
                     until=int(datetime.now(timezone.utc).timestamp()))
    if not data:
        return {"insights": "indisponibles (ajoute l'autorisation insights sur l'app Meta)"}
    return {"portee_semaine": data.get("reach"), "visites_profil": data.get("profile_views"),
            "clics_lien": data.get("website_clicks"), "comptes_engages": data.get("accounts_engaged")}
