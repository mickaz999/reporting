from . import instagram, tiktok, twitch, youtube

# Chaque collecteur renvoie un dict de stats, ou None si non configuré.
COLLECTORS = {
    "YouTube": youtube.collect,
    "Twitch": twitch.collect,
    "TikTok": tiktok.collect,
    "Instagram": instagram.collect,
}
