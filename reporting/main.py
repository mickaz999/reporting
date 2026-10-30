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
        if name == "Twitch":
            lives = data["publications_semaine"]
            lines.append(f"- Lives cette semaine : {len(lives)}")
            if lives:
                total = sum(_seconds(v.get("duree", "")) for v in lives)
                lines.append(f"- Temps de stream : {total // 3600} h {total % 3600 // 60:02d}")
                lines.append(f"- Vues des rediffusions : {sum(v['vues'] for v in lives):,}".replace(",", " "))
        else:
            lines.append(f"- Publications cette semaine : {len(data['publications_semaine'])}")

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


def github_models(prompt):
    """IA gratuite incluse dans GitHub Actions (GitHub Models, avec le jeton GITHUB_TOKEN)."""
    r = requests.post("https://models.github.ai/inference/chat/completions", headers={
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    }, json={
        "model": os.getenv("GITHUB_MODEL", "openai/gpt-4.1-mini"),
        "messages": [{"role": "user", "content": prompt}],
    }, timeout=120)
    if not r.ok or "json" not in r.headers.get("content-type", ""):
        raise RuntimeError(f"GitHub Models {r.status_code} : {r.text[:300]}")
    return r.json()["choices"][0]["message"]["content"]


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
        if os.getenv("GITHUB_TOKEN"):
            try:
                return github_models(prompt)
            except Exception:
                traceback.print_exc()  # quota dépassé, etc. : on retombe sur le rapport simple
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
