"""
Configuration for Music Curator — Instagram Reel → Spotify Pipeline.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(dotenv_path=Path(__file__).with_name(".env"))

# -----------------------------------------------------------------------------
# Genre Taxonomy (fixed — do not modify without updating DB schema)
# -----------------------------------------------------------------------------
GENRE_TAXONOMY = {
    "house":        "House / Dance",
    "techno":       "Techno / Industrial",
    "jungle-dnb":   "Jungle / DnB",
    "dub":          "Dub / Reggae",
    "triphop":      "Trip-Hop / Downtempo",
    "trance":       "Trance / Electronic",
    "ambient":      "Ambient / Atmospheric",
    "synthwave":    "Synthwave / Electronica",
    "experimental": "Experimental / Avant-garde",
    "hip-hop":      "Hip-Hop / Rap",
    "r-and-b":      "R&B / Funk / Soul",
    "jazz":         "Jazz",
    "classical":    "Classical",
    "latin":        "Latin / Cumbia",
    "world":        "World / Folk",
    "gems":         "Gems / Finds",
    "other":        "Other",
}

GENRE_SLUGS = list(GENRE_TAXONOMY.keys())

INSTAGEMS_PLAYLIST_ID = "2qPZw99zXfzgv1ip6gU2FI"

# Per-user mirror playlists
USER_MIRROR_PLAYLISTS = {
    "dp": "2qPZw99zXfzgv1ip6gU2FI",   # instaGems
    "mb": "0bMVMPuJ85HmYl05Y0jQ0y",   # meggyInstaGems
}

# -----------------------------------------------------------------------------
# Spotify Genre Tag → Taxonomy Slug Mapping
# Extend this dict as real tracks come through.
# Key: lowercase Spotify genre tag (from artist.genres)
# Value: taxonomy slug
# -----------------------------------------------------------------------------
SPOTIFY_GENRE_TO_SLUG = {
    # House / Dance
    "house": "house",
    "deep house": "house",
    "progressive house": "house",
    "melodic house": "house",
    "tech house": "house",
    "garage": "house",
    "uk garage": "house",
    "edm": "house",
    "electro house": "house",
    "dance": "house",
    "future house": "house",

    # Techno / Industrial
    "techno": "techno",
    "industrial": "techno",
    "minimal": "techno",
    "minimal techno": "techno",
    "acid techno": "techno",
    "industrial techno": "techno",
    "ebm": "techno",
    "electro": "techno",
    "idm": "techno",
    "glitch": "techno",

    # Jungle / DnB
    "drum and bass": "jungle-dnb",
    "dnb": "jungle-dnb",
    "jungle": "jungle-dnb",
    "liquid dnb": "jungle-dnb",
    "neurofunk": "jungle-dnb",
    "breakbeat": "jungle-dnb",
    "breaks": "jungle-dnb",
    "halftime": "jungle-dnb",
    "dub techno": "jungle-dnb",

    # Dub / Reggae
    "dub": "dub",
    "reggae": "dub",
    "dancehall": "dub",
    "roots reggae": "dub",
    "dub reggae": "dub",
    "ska": "dub",
    "rocksteady": "dub",
    "lovers rock": "dub",

    # Trip-Hop / Downtempo
    "trip hop": "triphop",
    "trip-hop": "triphop",
    "downtempo": "triphop",
    "chillhop": "triphop",
    "lo-fi": "triphop",
    "lo fi": "triphop",
    "lofi": "triphop",
    "abstract hip hop": "triphop",
    "chillwave": "triphop",
    "future beats": "triphop",

    # Trance / Electronic
    "trance": "trance",
    "progressive trance": "trance",
    "psytrance": "trance",
    "goa trance": "trance",
    "hard trance": "trance",
    "uplifting trance": "trance",
    "tech trance": "trance",
    "dubstep": "trance",
    "bass": "trance",
    "future bass": "trance",

    # Ambient / Atmospheric
    "ambient": "ambient",
    "drone": "ambient",
    "dark ambient": "ambient",
    "sound art": "ambient",
    "field recording": "ambient",
    "lowercase": "ambient",
    "ambient techno": "ambient",
    "space music": "ambient",
    "new age": "ambient",

    # Synthwave / Electronica
    "synthwave": "synthwave",
    "vaporwave": "synthwave",
    "retrowave": "synthwave",
    "outrun": "synthwave",
    "darksynth": "synthwave",
    "chiptune": "synthwave",
    "electropop": "synthwave",
    "synth pop": "synthwave",
    "future garage": "synthwave",
    "wonky": "synthwave",

    # Experimental / Avant-garde
    "experimental": "experimental",
    "noise": "experimental",
    "avant-garde": "experimental",
    "musique concrete": "experimental",
    "sound collage": "experimental",
    "electroacoustic": "experimental",
    "microhouse": "experimental",
    "leftfield": "experimental",
    "glitch hop": "experimental",

    # Hip-Hop / Rap
    "hip hop": "hip-hop",
    "hip-hop": "hip-hop",
    "rap": "hip-hop",
    "trap": "hip-hop",
    "drill": "hip-hop",
    "grime": "hip-hop",
    "boom bap": "hip-hop",
    "conscious hip hop": "hip-hop",
    "alternative hip hop": "hip-hop",
    "cloud rap": "hip-hop",
    "uk drill": "hip-hop",
    "ny drill": "hip-hop",

    # R&B / Funk / Soul
    "r&b": "r-and-b",
    "rnb": "r-and-b",
    "soul": "r-and-b",
    "neo soul": "r-and-b",
    "contemporary r&b": "r-and-b",
    "alternative r&b": "r-and-b",
    "funk": "r-and-b",
    "disco": "r-and-b",
    "quiet storm": "r-and-b",
    "boogie": "r-and-b",
    "philly soul": "r-and-b",

    # Jazz
    "jazz": "jazz",
    "bebop": "jazz",
    "hard bop": "jazz",
    "cool jazz": "jazz",
    "free jazz": "jazz",
    "fusion": "jazz",
    "jazz fusion": "jazz",
    "acid jazz": "jazz",
    "nu jazz": "jazz",
    "jazz rap": "jazz",
    "soul jazz": "jazz",
    "bossa nova": "jazz",

    # Classical
    "classical": "classical",
    "orchestral": "classical",
    "chamber music": "classical",
    "opera": "classical",
    "baroque": "classical",
    "romantic": "classical",
    "contemporary classical": "classical",
    "modern classical": "classical",
    "neoclassical": "classical",
    "minimalism": "classical",
    "piano": "classical",

    # Latin / Cumbia
    "latin": "latin",
    "cumbia": "latin",
    "salsa": "latin",
    "reggaeton": "latin",
    "latin pop": "latin",
    "bachata": "latin",
    "merengue": "latin",
    "vallenato": "latin",
    "latin jazz": "latin",
    "afrobeats": "latin",
    "afrobeat": "latin",

    # World / Folk
    "world": "world",
    "folk": "world",
    "indie folk": "world",
    "singer-songwriter": "world",
    "acoustic": "world",
    "bluegrass": "world",
    "country": "world",
    "celtic": "world",
    "flamenco": "world",
    "fado": "world",
    "traditional": "world",
}

# -----------------------------------------------------------------------------
# OpenRouter Configuration
# -----------------------------------------------------------------------------
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-5")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# -----------------------------------------------------------------------------
# Database Configuration
# -----------------------------------------------------------------------------
DB_PATH = Path(__file__).with_name("music_curator.db")

# -----------------------------------------------------------------------------
# yt-dlp Configuration
# -----------------------------------------------------------------------------
YDL_OPTS_BASE = {
    "quiet": True,
    "cookiesfrombrowser": ("chrome",),  # fallback: ("firefox",) or cookiefile="instagram_cookies.txt"
    "skip_download": True,
}

# -----------------------------------------------------------------------------
# AudD API Configuration
# -----------------------------------------------------------------------------
AUDD_API_URL = "https://api.audd.io/"
AUDD_API_KEY = os.getenv("AUDD_API_KEY")

# -----------------------------------------------------------------------------
# Spotify Configuration
# -----------------------------------------------------------------------------
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")
SPOTIFY_SCOPES = "playlist-modify-public playlist-modify-private playlist-read-private"

# Playlist naming convention
PLAYLIST_NAME_TEMPLATE = "Curated — {display_name}"

# -----------------------------------------------------------------------------
# Streamlit Configuration
# -----------------------------------------------------------------------------
STREAMLIT_PORT = 8502
STREAMLIT_HOST = "0.0.0.0"

# -----------------------------------------------------------------------------
# Vision Configuration (for multi-track reel support)
# -----------------------------------------------------------------------------
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://192.168.1.70:11434")
VISION_MODEL = os.getenv("VISION_MODEL", "gemma4:latest")
FRAME_INTERVAL_SECONDS = int(os.getenv("FRAME_INTERVAL_SECONDS", "2"))
MAX_SAMPLE_SECONDS = int(os.getenv("MAX_SAMPLE_SECONDS", "120"))

# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------
def validate_config() -> list[str]:
    """Return list of missing required environment variables."""
    missing = []
    required_vars = [
        ("AUDD_API_KEY", AUDD_API_KEY),
        ("SPOTIFY_CLIENT_ID", SPOTIFY_CLIENT_ID),
        ("SPOTIFY_CLIENT_SECRET", SPOTIFY_CLIENT_SECRET),
        ("OPENROUTER_API_KEY", os.getenv("OPENROUTER_API_KEY")),
    ]
    for name, value in required_vars:
        if not value:
            missing.append(name)
    return missing