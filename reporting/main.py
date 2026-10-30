"""Agent de reporting hebdomadaire pour Mickaz9 Gaming."""
import json
import os
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path

import base64

import anthropic
import requests

from .pdf import build_pdf
from .platforms import COLLECTORS
from .platforms._common import parse_date, since

HISTORY = Path(__file__).resolve().parent.parent / "data" / "history.json"
MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")


def load_history():
    return json.loads(HISTORY.read_text()) if HISTORY.exists() else []


def collect_all():
    stats, errors = {}, {}
    for name, collect in COLLECTORS.items():
        try:
            data = collect()
            if data is not None:
                stats[name] = data
        except Exception as e:  # une plateforme en panne ne bloque pas le rapport
            traceback.print_exc()
            errors[name] = str(e)
    return stats, errors


def fetch_extra(stats):
    """Stats avancées collectées par l'app maderino (YouTube Analytics, spectateurs et subs Twitch)."""
    url, secret = os.getenv("MADERINO_URL"), os.getenv("MADERINO_REPORT_SECRET")
    if not (url and secret):
        return
    try:
        extra = requests.get(f"{url.rstrip('/')}/api/report/extra", headers={"Authorization": f"Bearer {secret}"},
                             timeout=60).json()
    except Exception:
        traceback.print_exc()
        return
    for name, key in (("YouTube", "youtube"), ("Twitch", "twitch")):
        if extra.get(key) and name in stats:
            stats[name]["avance"] = extra[key]


def keep_last_week(stats):
    """Ne garde que les publications des 7 derniers jours."""
    limit = since()
    for data in stats.values():
        data["publications_semaine"] = [
            p for p in data.pop("dernieres_publications", [])
            if p.get("date") and parse_date(p["date"]) >= limit
        ]
    return stats


LABELS = {
    "abonnes": "Abonnés", "followers": "Followers", "vues_totales": "Vues totales",
    "nb_videos": "Vidéos", "likes_totaux": "Likes totaux", "nb_publications": "Publications",
}


def _seconds(duree):
    """Durée Twitch (« 3h2m10s ») en secondes."""
    return sum(int(n) * {"h": 3600, "m": 60, "s": 1}[u] for n, u in re.findall(r"(\d+)([hms])", duree))


def _human(duree):
    t = _seconds(duree)
    return f"{t // 3600} h {t % 3600 // 60:02d}" if t >= 3600 else f"{t // 60} min"


TRAFIC = {"YT_SEARCH": "Recherche YouTube", "SUBSCRIBER": "Abonnés", "RELATED_VIDEO": "Vidéos suggérées",
          "YT_OTHER_PAGE": "Autres pages YouTube", "EXT_URL": "Sites externes", "SHORTS": "Flux Shorts",
          "BROWSE": "Accueil / navigation", "NO_LINK_OTHER": "Accès direct", "PLAYLIST": "Playlists",
          "NOTIFICATION": "Notifications", "YT_CHANNEL": "Page de la chaîne", "END_SCREEN": "Écrans de fin",
          "HASHTAGS": "Hashtags", "SOUND_PAGE": "Pages de sons", "LIVE_REDIRECT": "Redirections de live"}


GENRES = {"male": "hommes", "female": "femmes", "user_specified": "autres"}


def _n(x):
    return f"{x:,}".replace(",", " ")


def _youtube_extra(a):
    if not a:
        return []
    if a.get("erreur"):
        return [f"- Stats avancées indisponibles : {a['erreur']}"]
    out = [f"- Sur la période {a['periode']} (données YouTube Analytics) :",
           f"- Durée de visionnage : {_n(round(a.get('estimatedMinutesWatched', 0) / 60))} h",
           f"- Durée moyenne vue : {int(a.get('averageViewDuration', 0)) // 60} min {int(a.get('averageViewDuration', 0)) % 60:02d} s"
           f" ({round(a.get('averageViewPercentage', 0))} % de la vidéo)",
           f"- Abonnés : +{_n(a.get('subscribersGained', 0))} / -{_n(a.get('subscribersLost', 0))}"]
    if a.get("sources_trafic"):
        out.append("- Sources de trafic : " + ", ".join(
            f"{TRAFIC.get(t['insightTrafficSourceType'], t['insightTrafficSourceType'])} ({_n(t['views'])})" for t in a["sources_trafic"]))
    if a.get("pays"):
        out.append("- Pays : " + ", ".join(f"{p['country']} ({_n(p['views'])})" for p in a["pays"]))
    if a.get("appareils"):
        out.append("- Appareils : " + ", ".join(f"{d['deviceType'].lower()} ({_n(d['views'])})" for d in a["appareils"]))
    top = sorted(a.get("audience", []), key=lambda x: -x["pourcentage"])[:3]
    if top:
        out.append("- Audience principale : " + ", ".join(
            f"{GENRES.get(x['genre'], x['genre'])} {x['age'].replace('age', '')} ans ({round(x['pourcentage'])} %)" for x in top))
    return out


def _twitch_extra(a):
    if not a:
        return []
    if a.get("erreur"):
        return [f"- Stats avancées indisponibles : {a['erreur']}"]
    out = []
    if a.get("spectateurs_moyens") is not None:
        out.append(f"- Spectateurs moyens : {a['spectateurs_moyens']} (pic : {a['pic_spectateurs']})")
    if a.get("subs") is not None:
        t = a["subs_par_tier"]
        out.append(f"- Subs : {a['subs']} (tier 1 : {t['1']}, tier 2 : {t['2']}, tier 3 : {t['3']} ; dont {a['subs_offerts']} offerts)")
    if a.get("nouveaux_followers") is not None:
        names = ", ".join(a["noms_nouveaux_followers"][:10])
        out.append(f"- Nouveaux followers : {a['nouveaux_followers']}" + (f" ({names})" if names else ""))
    if a.get("top_bits"):
        out.append("- Top bits : " + ", ".join(f"{b['pseudo']} ({_n(b['bits'])})" for b in a["top_bits"]))
    if a.get("nb_clips"):
        best = a["clips"][0]
        out.append(f"- Clips créés : {a['nb_clips']} (meilleur : {best['titre']} · {_n(best['vues'])} vues)")
    if a.get("erreur_connexion"):
        out.append(f"- Connexion Twitch à refaire : {a['erreur_connexion']}")
    return out


def basic_report(stats, previous, errors):
    """Rapport sans IA (gratuit) : chiffres, évolution et top 3."""
    previous = previous or {}
    lines = ["# Chiffres clés"]
    for name, data in stats.items():
        lines.append(f"## {name}")
        for key, label in LABELS.items():
            if key not in data:
                continue
            old = previous.get(name, {}).get(key)
            delta = f" ({data[key] - old:+,})".replace(",", " ") if old is not None else ""
            lines.append(f"- {label} : {data[key]:,}{delta}".replace(",", " "))
        if name == "Twitch" and data.get("en_live"):
            lines.append(f"- 🔴 En live : {data['spectateurs_actuels']} spectateurs")
        if name == "YouTube":
            pubs = data["publications_semaine"]
            shorts = sum(1 for p in pubs if p.get("format") == "Short")
            lines.append(f"- Publications cette semaine : {len(pubs)} ({shorts} Shorts, {len(pubs) - shorts} vidéos)")
            lines += _youtube_extra(data.get("avance"))
        elif name == "Twitch":
            lives = data["publications_semaine"]
            lines.append(f"- Lives cette semaine : {len(lives)}")
            if lives:
                total = sum(_seconds(v.get("duree", "")) for v in lives)
                lines.append(f"- Temps de stream : {total // 3600} h {total % 3600 // 60:02d}")
                lines.append(f"- Vues des rediffusions : {sum(v['vues'] for v in lives):,}".replace(",", " "))
            lines += _twitch_extra(data.get("avance"))
        else:
            lines.append(f"- Publications cette semaine : {len(data['publications_semaine'])}")
        if name == "Instagram":
            for key, label in (("portee_semaine", "Portée de la semaine"), ("visites_profil", "Visites du profil"),
                               ("clics_lien", "Clics sur le lien"), ("comptes_engages", "Comptes engagés")):
                if data.get(key) is not None:
                    lines.append(f"- {label} : {data[key]:,}".replace(",", " "))

    posts = [(name, p) for name, data in stats.items() if name != "Twitch" for p in data["publications_semaine"]]
    score = lambda p: p.get("vues") or p.get("likes", 0)
    lines.append("# Top 3 des vidéos et publications")
    if not posts:
        lines.append("Aucune publication cette semaine.")
    for name, p in sorted(posts, key=lambda x: score(x[1]), reverse=True)[:3]:
        what = f"{p['vues']:,} vues" if p.get("vues") else f"{p.get('likes', 0):,} likes"
        lines.append(f"- {name} · {p['titre'] or 'Sans titre'} · {what}".replace(",", " "))
        if p.get("lien"):
            lines.append(p["lien"])

    lives = stats.get("Twitch", {}).get("publications_semaine", [])
    if lives:
        best = max(lives, key=lambda v: v["vues"])
        lines.append("# Meilleur live Twitch")
        lines.append(f"- {best['titre'] or 'Sans titre'} · live de {_human(best.get('duree', ''))} · {best['vues']:,} vues en rediff".replace(",", " "))
        lines.append(best["lien"])

    if errors:
        lines.append("# Plateformes en erreur")
        lines += [f"- {name} : {msg}" for name, msg in errors.items()]
    return "\n".join(lines)


def summarize(stats, previous, errors):
    prompt = f"""Tu es l'analyste réseaux sociaux de la chaîne gaming « Mickaz9 Gaming ».
Rédige en français le bilan de la semaine écoulée (7 derniers jours), en Markdown compatible Discord (pas de tableaux), 3500 caractères max :
1. Chiffres clés par plateforme avec l'évolution depuis la semaine dernière (+X / -X)
2. Nombre de publications de la semaine par plateforme et top 3 des contenus, toutes plateformes confondues
3. Tendances et points d'attention
4. 3 conseils concrets pour la semaine prochaine

Vocabulaire : sur Twitch, parle de lives, de followers, de temps de stream et de vues des rediffusions (VOD) ;
« publications_semaine » de Twitch = les lives de la semaine. Sur YouTube, TikTok et Instagram, parle de vidéos / publications et d'abonnés.

Stats actuelles : {json.dumps(stats, ensure_ascii=False)}
Stats de la semaine dernière : {json.dumps(previous, ensure_ascii=False) if previous else "aucune (premier rapport)"}
Plateformes en erreur : {json.dumps(errors, ensure_ascii=False) if errors else "aucune"}"""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return basic_report(stats, previous, errors)
    msg = anthropic.Anthropic().messages.create(
        model=MODEL, max_tokens=2000, messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in msg.content if b.type == "text")


def send_maderino(title, text):
    """Dépose le rapport comme page dans l'app maderino (dépôt mickaz999/Copy-app)."""
    url, secret = os.getenv("MADERINO_URL"), os.getenv("MADERINO_REPORT_SECRET")
    if not (url and secret):
        return False
    pdf = base64.b64encode(build_pdf(title, text)).decode()
    requests.post(f"{url.rstrip('/')}/api/report", json={"title": title, "markdown": text, "pdf": pdf},
                  headers={"Authorization": f"Bearer {secret}"}, timeout=30).raise_for_status()
    return True


def send_discord(text):
    url = os.getenv("DISCORD_WEBHOOK_URL")
    if not url:
        return False
    requests.post(url, json={
        "username": "Mickaz9 Reporting",
        "embeds": [{
            "title": f"📊 Rapport Mickaz9 Gaming — {datetime.now():%d/%m/%Y}",
            "description": text[:4096],
            "color": 0x9146FF,
        }],
    }, timeout=30).raise_for_status()
    return True


def main():
    history = load_history()
    stats, errors = collect_all()
    stats = keep_last_week(stats)
    fetch_extra(stats)
    if not stats:
        raise SystemExit("Aucune plateforme configurée : renseigne les secrets (voir README).")
    today = datetime.now(timezone.utc).date().isoformat()
    older = [h for h in history if h["date"][:10] != today]
    previous = older[-1]["stats"] if older else None
    report = summarize(stats, previous, errors)
    sent_maderino = send_maderino(f"Rapport du {datetime.now():%d/%m/%Y}", report)
    sent_discord = send_discord(report)
    if not (sent_maderino or sent_discord):
        print(report)

    now = datetime.now(timezone.utc)
    # Un seul point par jour : un relancement manuel remplace celui du jour
    history = [h for h in history if h["date"][:10] != now.date().isoformat()]
    history.append({"date": now.isoformat(), "stats": stats})
    HISTORY.parent.mkdir(exist_ok=True)
    HISTORY.write_text(json.dumps(history[-52:], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
