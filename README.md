# Mickaz9 Gaming – Agent de reporting

Chaque dimanche soir, cet agent fait le bilan des 7 derniers jours :
1. récupère les stats **YouTube, Twitch, TikTok et Instagram** ;
2. ne garde que les publications de la semaine et compare les chiffres à la semaine précédente (historique dans `data/history.json`) ;
3. demande à Claude de rédiger une analyse avec des conseils ;
4. envoie le rapport sur **Discord**.

Une plateforme sans secrets est simplement ignorée : tu peux commencer avec YouTube et Twitch, puis ajouter les autres.

## Configuration (GitHub → Settings → Secrets and variables → Actions)

| Secret | Où l'obtenir |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `DISCORD_WEBHOOK_URL` | Salon Discord → Modifier → Intégrations → Webhooks |
| `YOUTUBE_API_KEY` | Google Cloud Console → activer *YouTube Data API v3* → Identifiants → Clé API |
| `YOUTUBE_CHANNEL_ID` | ton pseudo YouTube (ex. `@mickaz9`) ou l'ID de chaîne qui commence par `UC` |
| `TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET` | dev.twitch.tv/console → Enregistrer une application |
| `TWITCH_LOGIN` | ton pseudo Twitch |
| `TIKTOK_CLIENT_KEY` / `TIKTOK_CLIENT_SECRET` | developers.tiktok.com → app avec *Login Kit*, scopes `user.info.basic`, `user.info.stats`, `video.list` |
| `TIKTOK_REFRESH_TOKEN` | obtenu après t'être connecté une fois via l'OAuth TikTok (valable 1 an) |
| `INSTAGRAM_ACCESS_TOKEN` | compte Instagram **Pro** relié à une Page Facebook, app Meta avec `instagram_basic` ; token longue durée (60 jours, à renouveler) |
| `INSTAGRAM_ACCOUNT_ID` | ID du compte Instagram Business (via Graph API Explorer : `me/accounts?fields=instagram_business_account`) |

## Lancer

- Manuellement : onglet **Actions** → *Rapport hebdo Mickaz9* → **Run workflow**.
- En local :
  ```bash
  pip install -r requirements.txt
  export YOUTUBE_API_KEY=... ANTHROPIC_API_KEY=...   # etc.
  python -m reporting.main
  ```
  Sans `DISCORD_WEBHOOK_URL`, le rapport s'affiche dans le terminal.
