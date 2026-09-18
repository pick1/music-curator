"""
Track identification from Instagram Reel metadata.

Two-stage identification:
1. Parse caption/description for artist/track patterns
2. Fallback: AudD audio fingerprint API
"""

import re
import subprocess
import os
import requests
from typing import Optional

from config import AUDD_API_URL, AUDD_API_KEY


# -----------------------------------------------------------------------------
# Stage 1: Caption Parsing
# -----------------------------------------------------------------------------

# Common patterns found in Instagram Reel captions
CAPTION_PATTERNS = [
    # "@handle - Track Name" or "Artist - Track Name" (Instagram music reel)
    (r"@?([\w][\w\s]+?)\s*-\s*([^\n@]+)", "artist_track"),
    # "🎵 Track Name - Artist Name"
    (r"[🎵🎶]\s*([^-\n]+?)\s*-\s*([^\n]+)", "track_artist"),
    # "Track Name - Artist Name" (without emoji, at start of line)
    (r"^([^-\n]+?)\s*-\s*([^\n]+)$", "track_artist"),
    # "Song: Track Name by Artist Name"
    (r"[Ss]ong:\s*([^-\n]+?)\s*(?:by|[-–])\s*([^\n]+)", "track_artist"),
    # "Track: X by Y"
    (r"[Tt]rack:\s*([^-\n]+?)\s*(?:by|[-–])\s*([^\n]+)", "track_artist"),
    # "Original audio · Artist Name" or "Original audio • Artist Name"
    (r"[Oo]riginal\s+audio\s*[·•]\s*([^\n]+)", "artist_only"),
    # "Audio: Artist - Track" or "Audio: Track - Artist"
    (r"[Aa]udio:\s*([^-\n]+?)\s*-\s*([^\n]+)", "track_artist"),
    # "Music: Artist - Track"
    (r"[Mm]usic:\s*([^-\n]+?)\s*-\s*([^\n]+)", "track_artist"),
    # "Artist · Track" or "Artist • Track" (common format)
    (r"^([^·•\n]+)\s*[·•]\s*([^·•\n]+)$", "artist_track"),
]

# Clean up extracted strings
def _clean(text: str) -> str:
    """Clean extracted text."""
    text = text.strip()
    # Remove trailing hashtags, mentions, URLs
    text = re.sub(r"@(\w+)", r"\1", text)
    text = re.sub(r"\s*#\w+", "", text)
    text = re.sub(r"\s*https?://\S+", "", text)
    # Remove emojis
    text = re.sub(r"[🎵🎶🎧🔊🎤🎸🎹🎺🎻🥁🎷🎶]", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


JUNK_WORDS = {"dj", "producer", "artist", "music", "song", "track", "audio", "sound", "beats", "official"}

SENTENCE_WORDS = {
    "the", "and", "that", "this", "with", "from", "were", "very", "same",
    "time", "coming", "out", "wider", "deep", "into", "about", "their",
    "have", "been", "which", "they", "also", "some", "when", "what",
    "there", "where", "would", "could", "should", "through", "after",
}

def _looks_like_sentence(text: str) -> bool:
    if not text:
        return False
    words = text.lower().split()
    if len(words) > 6:
        return True
    return sum(1 for w in words if w in SENTENCE_WORDS) >= 2

def _is_valid(artist: str, track: str) -> bool:
    if artist.startswith('#') or track.startswith('#'):
        return False
    if not artist or not track:
        return False
    if len(track) > 80 or len(artist) > 60:
        return False
    if track.lower() in JUNK_WORDS or artist.lower() in JUNK_WORDS:
        return False
    if _looks_like_sentence(track) or _looks_like_sentence(artist):
        return False
    return True

def parse_caption(caption: str) -> Optional[dict]:
    """
    Parse Instagram caption for track/artist info.

    Returns:
        dict with artist, track, album (optional), confidence
        or None if no match
    """
    if not caption:
        return None

    lines = caption.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue

        for pattern, ptype in CAPTION_PATTERNS:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                groups = match.groups()
                if ptype == "track_artist":
                    track = _clean(groups[0])
                    artist = _clean(groups[1])
                    # Sanity check — long strings are likely bio text, not track titles
                    if _is_valid(artist, track):
                        return {
                            "artist": artist,
                            "track": track,
                            "album": None,
                            "id_method": "caption",
                            "confidence": "high",
                        }
                elif ptype == "artist_only":
                    artist = _clean(groups[0])
                    if artist:
                        return {
                            "artist": artist,
                            "track": None,
                            "album": None,
                            "id_method": "caption",
                            "confidence": "medium",
                        }
                elif ptype == "artist_track":
                    artist = _clean(groups[0])
                    track = _clean(groups[1])
                    if _is_valid(artist, track):
                        return {
                            "artist": artist,
                            "track": track,
                            "album": None,
                            "id_method": "caption",
                            "confidence": "high",
                        }
                elif ptype == "hashtag_pair":
                    # Less reliable, but could work for simple cases
                    artist = _clean(groups[0])
                    track = _clean(groups[1])
                    if artist and track:
                        return {
                            "artist": artist,
                            "track": track,
                            "album": None,
                            "id_method": "caption",
                            "confidence": "low",
                        }

    return None


# -----------------------------------------------------------------------------
# Stage 2: AudD Audio Fingerprinting
# -----------------------------------------------------------------------------


def identify_with_acoustid(audio_path: str) -> Optional[dict]:
    """Identify track using AcoustID + Chromaprint. Free, no quota."""
    import os, json, subprocess, requests
    api_key = os.getenv("ACOUSTID_API_KEY")
    if not api_key or not os.path.exists(audio_path):
        return None
    try:
        result = subprocess.run(
            ["fpcalc", "-json", audio_path],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return None
        fp_data = json.loads(result.stdout)
        duration = fp_data["duration"]
        fingerprint = fp_data["fingerprint"]
        response = requests.get("https://api.acoustid.org/v2/lookup", params={
            "client": api_key,
            "duration": int(duration),
            "fingerprint": fingerprint,
            "meta": "recordings releases",
        }, timeout=10)
        data = response.json()
        results = data.get("results", [])
        if not results:
            return None
        best = results[0]
        if best.get("score", 0) < 0.7:
            return None
        recordings = best.get("recordings", [])
        if not recordings:
            return None
        rec = recordings[0]
        title = rec.get("title")
        artists = [a["name"] for a in rec.get("artists", [])]
        if not title or not artists:
            return None
        return {
            "artist": ", ".join(artists),
            "track": title,
            "album": None,
            "id_method": "acoustid",
            "confidence": "high",
        }
    except Exception as e:
        return {"error": f"AcoustID failed: {e}"}


def identify_with_audd(audio_path: str) -> Optional[dict]:
    """
    Identify track using AudD API.

    Args:
        audio_path: Path to MP3 file

    Returns:
        dict with artist, track, album, or None if failed
    """
    if not AUDD_API_KEY:
        return {"error": "AUDD_API_KEY not configured"}

    if not os.path.exists(audio_path):
        return {"error": f"Audio file not found: {audio_path}"}

    try:
        with open(audio_path, "rb") as f:
            files = {"file": f}
            data = {
                "api_token": AUDD_API_KEY,
                "return": "apple_music,spotify",
            }
            response = requests.post(AUDD_API_URL, files=files, data=data, timeout=30)
            response.raise_for_status()
            result = response.json()

        if result.get("status") != "success" or not result.get("result"):
            return {"error": f"AudD returned no result: {result}"}

        audd_result = result["result"]
        return {
            "artist": audd_result.get("artist"),
            "track": audd_result.get("title"),
            "album": audd_result.get("album"),
            "id_method": "audd",
            "confidence": "high",
            "spotify_id": audd_result.get("spotify", {}).get("id") if audd_result.get("spotify") else None,
            "apple_music_id": audd_result.get("apple_music", {}).get("id") if audd_result.get("apple_music") else None,
            "timecode": audd_result.get("timecode"),
        }

    except requests.RequestException as e:
        return {"error": f"AudD request failed: {e}"}
    except Exception as e:
        return {"error": f"AudD processing failed: {e}"}


# -----------------------------------------------------------------------------
# Multi-track Detection
# -----------------------------------------------------------------------------

def looks_like_instagram_handle(text: str) -> bool:
    """Return True if text looks like an Instagram handle rather than an artist name."""
    import re
    if not text:
        return False
    # Handles: all lowercase/digits, no spaces, often ends in music/official/dj etc
    text = text.strip().lower()
    if ' ' in text:
        return False  # real artist names usually have spaces or caps
    if re.match(r'^[a-z0-9._]+$', text) and len(text) > 4:
        return True
    return False


def is_multi_track_caption(caption: str) -> bool:
    """
    Detect captions that indicate a multi-track reel.
    e.g. "3 tracks that...", "top 5 songs", "playlist of..."
    """
    patterns = [
        r'\b\d+\s+tracks?\b',
        r'\b\d+\s+songs?\b',
        r'\btop\s+\d+\s+tracks?\b',
        r'\btop\s+\d+\s+songs?\b',
        r'(?<![a-z])part\s+\d+\b',
    ]
    caption_lower = caption.lower()
    return any(re.search(p, caption_lower) for p in patterns)


# -----------------------------------------------------------------------------
# Main Identification Function
# -----------------------------------------------------------------------------

def identify_track(info: dict, audio_path: Optional[str] = None) -> dict:
    """
    Identify track from reel info and optional audio file.

    Args:
        info: Dict from extractor.extract_reel_info() with title, description, uploader
        audio_path: Optional path to downloaded MP3 for fingerprinting

    Returns:
        dict with artist, track, album, id_method, confidence
    """
    # Combine caption sources
    caption_parts = []
    if info.get("title"):
        caption_parts.append(info["title"])
    if info.get("description"):
        caption_parts.append(info["description"])
    if info.get("uploader"):
        caption_parts.append(info["uploader"])
    caption = "\n".join(caption_parts)

    # Check for multi-track reel BEFORE caption parse
    if is_multi_track_caption(caption):
        return {
            "artist": None,
            "track": None,
            "album": None,
            "id_method": "multi_track_detected",
            "confidence": "none",
            "multi_track": True,
        }

    # Stage 1: Try caption parsing
    caption_result = parse_caption(caption)
    if caption_result and caption_result.get("artist") and caption_result.get("track"):
        return caption_result

    # Stage 2: Try AcoustID first (free), then AudD fallback
    if audio_path:
        acoustid_result = identify_with_acoustid(audio_path)
        if acoustid_result and not acoustid_result.get("error") and acoustid_result.get("track"):
            return acoustid_result
        # AcoustID missed — log and fall back to AudD
        acoustid_miss = acoustid_result.get("error") if acoustid_result else "no match"
        print(f"[identifier] AcoustID miss: {acoustid_miss} — trying AudD")
        audd_result = identify_with_audd(audio_path)
        if audd_result and not audd_result.get("error"):
            return {**audd_result, "acoustid_miss": acoustid_miss}
        # AudD also failed
        audd_error = audd_result.get("error") if audd_result else "no result"
        print(f"[identifier] AudD failed: {audd_error}")
        # Check if AudD quota exhausted
        if audd_result and ("limit" in str(audd_error).lower() or "quota" in str(audd_error).lower() or "trial" in str(audd_error).lower()):
            return {
                "artist": None, "track": None, "album": None,
                "id_method": "failed",
                "confidence": "none",
                "error": "AudD quota exhausted — renew plan or switch to paid tier",
                "audd_quota_exhausted": True,
            }

    # If caption gave us partial info (artist only), return that
    if caption_result:
        return caption_result

    # Total failure
    return {
        "artist": None,
        "track": None,
        "album": None,
        "id_method": "failed",
        "confidence": "none",
        "error": "Could not identify track from caption or audio",
    }