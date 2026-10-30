"""Agent de reporting hebdomadaire pour Mickaz9 Gaming."""
import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import requests

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
        lines.append(f"- Publications cette semaine : {len(data['publications_semaine'])}")

    posts = [(name, p) for name, data in stats.items() for p in data["publications_semaine"]]
    score = lambda p: p.get("vues") or p.get("likes", 0)
    lines.append("# Top 3 de la semaine")
    if not posts:
        lines.append("Aucune publication cette semaine.")
    for name, p in sorted(posts, key=lambda x: score(x[1]), reverse=True)[:3]:
        what = f"{p['vues']:,} vues" if p.get("vues") else f"{p.get('likes', 0):,} likes"
        lines.append(f"- {name} · {p['titre'] or 'Sans titre'} · {what}".replace(",", " "))
        if p.get("lien"):
            lines.append(p["lien"])

    if errors:
        lines.append("# Plateformes en erreur")
        lines += [f"- {name} : {msg}" for name, msg in errors.items()]
    return "\n".join(lines)


def summarize(stats, previous, errors):
    if not os.getenv("ANTHROPIC_API_KEY"):
        return basic_report(stats, previous, errors)
    prompt = f"""Tu es l'analyste réseaux sociaux de la chaîne gaming « Mickaz9 Gaming ».
Rédige en français le bilan de la semaine écoulée (7 derniers jours), en Markdown compatible Discord (pas de tableaux), 3500 caractères max :
1. Chiffres clés par plateforme avec l'évolution depuis la semaine dernière (+X / -X)
2. Nombre de publications de la semaine par plateforme et top 3 des contenus, toutes plateformes confondues
3. Tendances et points d'attention
4. 3 conseils concrets pour la semaine prochaine

Stats actuelles : {json.dumps(stats, ensure_ascii=False)}
Stats de la semaine dernière : {json.dumps(previous, ensure_ascii=False) if previous else "aucune (premier rapport)"}
Plateformes en erreur : {json.dumps(errors, ensure_ascii=False) if errors else "aucune"}"""
    msg = anthropic.Anthropic().messages.create(
        model=MODEL, max_tokens=2000, messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in msg.content if b.type == "text")


def send_maderino(title, text):
    """Dépose le rapport comme page dans l'app maderino (dépôt mickaz999/Copy-app)."""
    url, secret = os.getenv("MADERINO_URL"), os.getenv("MADERINO_REPORT_SECRET")
    if not (url and secret):
        return False
    requests.post(f"{url.rstrip('/')}/api/report", json={"title": title, "markdown": text},
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
    if not stats:
        raise SystemExit("Aucune plateforme configurée : renseigne les secrets (voir README).")
    previous = history[-1]["stats"] if history else None
    report = summarize(stats, previous, errors)
    sent_maderino = send_maderino(f"Rapport du {datetime.now():%d/%m/%Y}", report)
    sent_discord = send_discord(report)
    if not (sent_maderino or sent_discord):
        print(report)

    history.append({"date": datetime.now(timezone.utc).isoformat(), "stats": stats})
    HISTORY.parent.mkdir(exist_ok=True)
    HISTORY.write_text(json.dumps(history[-52:], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
