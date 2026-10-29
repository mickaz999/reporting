"""Agent de reporting hebdomadaire pour Mickaz9 Gaming."""
import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import requests

from .platforms import COLLECTORS

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


def summarize(stats, previous, errors):
    prompt = f"""Tu es l'analyste réseaux sociaux de la chaîne gaming « Mickaz9 Gaming ».
Rédige en français le rapport hebdomadaire, en Markdown compatible Discord (pas de tableaux), 3500 caractères max :
1. Chiffres clés par plateforme avec l'évolution depuis la semaine dernière (+X / -X)
2. Top 3 des contenus de la semaine, toutes plateformes confondues
3. Tendances et points d'attention
4. 3 conseils concrets pour la semaine prochaine

Stats actuelles : {json.dumps(stats, ensure_ascii=False)}
Stats de la semaine dernière : {json.dumps(previous, ensure_ascii=False) if previous else "aucune (premier rapport)"}
Plateformes en erreur : {json.dumps(errors, ensure_ascii=False) if errors else "aucune"}"""
    msg = anthropic.Anthropic().messages.create(
        model=MODEL, max_tokens=2000, messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in msg.content if b.type == "text")


def send_discord(text):
    url = os.getenv("DISCORD_WEBHOOK_URL")
    if not url:
        print(text)
        return
    requests.post(url, json={
        "username": "Mickaz9 Reporting",
        "embeds": [{
            "title": f"📊 Rapport Mickaz9 Gaming — {datetime.now():%d/%m/%Y}",
            "description": text[:4096],
            "color": 0x9146FF,
        }],
    }, timeout=30).raise_for_status()


def main():
    history = load_history()
    stats, errors = collect_all()
    if not stats:
        raise SystemExit("Aucune plateforme configurée : renseigne les secrets (voir README).")
    previous = history[-1]["stats"] if history else None
    send_discord(summarize(stats, previous, errors))

    history.append({"date": datetime.now(timezone.utc).isoformat(), "stats": stats})
    HISTORY.parent.mkdir(exist_ok=True)
    HISTORY.write_text(json.dumps(history[-52:], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
