# Music Curator — Instagram Reel → Spotify Pipeline

A Streamlit app that accepts an Instagram Reel URL, identifies the track playing in it, classifies it into a genre, and either adds it to the correct Spotify playlist or flags it for manual review.

## Project Structure

```
music-curator/
├── app.py                  # Streamlit entry point (3 tabs: Add, Library, Flagged)
├── config.py               # Genre taxonomy, keyword mapping, constants
├── db.py                   # SQLite wrapper (tracks & playlists tables)
├── extractor.py            # yt-dlp wrapper for Instagram Reels
├── identifier.py           # Caption parsing + AudD audio fingerprinting
├── genre.py                # Genre classification (Spotify mapping + OpenRouter fallback)
├── spotify_client.py       # Spotify Web API client (OAuth2, search, playlist CRUD)
├── .env.example            # Template for environment variables
├── requirements.txt        # Python dependencies
├── music_curator.db        # SQLite database (created on first run)
├── music-curator.service   # Systemd service template
└── README.md               # This file
```

## Features

- **Instagram Reel Processing**: Extract metadata and audio using yt-dlp
- **Track Identification**: 
  - Stage 1: Parse caption/description for artist/track patterns
  - Stage 2: Fallback to AudD audio fingerprint API
- **Genre Classification**:
  - Map Spotify artist genres to fixed taxonomy
  - OpenRouter LLM fallback for ambiguous/missing genres
  - Taxonomy: electronic, ambient, hip-hop, r-and-b, jazz, classical, rock, pop, latin, world, metal, other
- **Spotify Integration**:
  - Search for tracks by artist/title
  - Get artist genre tags
  - Create or find playlists by genre
  - Add tracks to playlists (with deduplication)
- **Manual Review UI**: Flag low-confidence classifications for human review
- **Persistence**: SQLite database stores all processing history
- **Streamlit UI**: Three-tab interface for adding tracks, browsing library, reviewing flagged items

## Installation

1. **Clone/Copy**: Place this directory on your target host (e.g., floorBoard at 192.168.1.70)

2. **Install Dependencies**:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure Environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your actual API keys:
   # - AUDD_API_KEY (from audd.io)
   # - SPOTIFY_CLIENT_ID & SPOTIFY_CLIENT_SECRET (from Spotify Developer Dashboard)
   # - OPENROUTER_API_KEY (from openrouter.ai)
   ```

4. **Initialize Database**:
   ```bash
   python -c "from db import init_db; init_db()"
   ```

5. **Optional: Set up Systemd Service**:
   - Copy `music-curator.service` to `~/.config/systemd/user/`
   - Edit the service file to match your username and paths
   - Enable and start: `systemctl --user daemon-reload && systemctl --user enable --now music-curator`

## Usage

1. Start the application:
   ```bash
   source venv/bin/activate
   streamlit run app.py --server.port 8502
   ```

2. Open your browser to `http://localhost:8502` (or configure proxy/tunnel for remote access)

3. **Add Track Tab**:
   - Paste an Instagram Reel URL
   - Click "Process Reel"
   - Watch the pipeline progress through extraction → identification → Spotify search → genre classification → routing
   - Result shows success (added to Spotify), flagged for review, or error

4. **Library Tab**:
   - Browse recently processed tracks
   - Filter by genre or show flagged items only
   - View track details and classification reasoning

5. **Flagged Tab**:
   - Review tracks requiring manual intervention
   - Select correct genre from taxonomy
   - Mark as resolved or defer for later

## Architecture Overview

```text
Instagram Reel URL
        │
        ▼
[1] yt-dlp — extract audio + caption metadata
        │
        ▼
[2] Identify track
    ├─ Try: parse caption for artist/track name (regex + heuristics)
    └─ Fallback: AudD API audio fingerprint
        │
        ▼
[3] Spotify search — look up artist/track
    ├─ Found → fetch Spotify genre tags
    └─ Not found → flag entry, skip to [6]
        │
        ▼
[4] Genre classification
    ├─ If Spotify genre is unambiguous → map to taxonomy
    ├─ If genre is absent or ambiguous → call OpenRouter API to classify
    │   (pass: artist, track, album, Spotify genre tags, caption)
    └─ If confidence still low → surface manual review UI
        │
        ▼
[5] Route
    ├─ Spotify playlist exists for genre → add track
    └─ Playlist doesn't exist yet → create it, then add track
        │
        ▼
[6] Persist to SQLite + update Streamlit UI
```

## Configuration

All secrets are stored in `.env` (gitignored):

```env
AUDD_API_KEY=
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=http://localhost:8888/callback
OPENROUTER_API_KEY=
OPENROUTER_MODEL=deepseek/deepseek-chat-v3-5
```

## Dependencies

- streamlit
- yt-dlp
- spotipy
- openai
- python-dotenv
- requests

## Notes

- Instagram extraction requires authentication: Uses `--cookies-from-browser chrome` by default
  - Requires being logged into Instagram in Chrome on the host machine
  - Fallback: export cookies via browser extension to `instagram_cookies.txt`
- Spotify OAuth: Initial auth requires visiting the authorization URL and caching the token
- OpenRouter: Used only when Spotify genre mapping fails or is ambiguous
- Database: SQLite file `music_curator.db` created in project directory
- Port: Streamlit runs on port 8502 by default (configurable in app.py)

## Testing

Run the verification script:
```bash
python -c "
import sys
sys.path.insert(0, '.')
from config import validate_config
from db import init_db
print('Config valid:', not validate_config())
init_db()
print('Database initialized')
"
```

## Deployment on floorBoard

1. Place project in `/home/dp/projects/music-curator/`
2. Create venv and install dependencies
3. Configure `.env` with actual API keys
4. Test manually: `source venv/bin/activate && streamlit run app.py`
5. Set up systemd service (see `music-curator.service` template)
6. Optionally expose via Cloudflare Tunnel at `music.sequoiaanalytics.com`

---
*Built as part of the Hermes Agent ecosystem. Designed to run on floorBoard alongside SIGNAL/distillate, LocalLens, and other services.*