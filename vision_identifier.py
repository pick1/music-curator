"""
Multi-track identification via Gemma4 vision + frame sampling.
Uses local Ollama at http://192.168.1.70:11434.
"""

import os
import re
import json
import base64
import subprocess
import tempfile
import requests
from typing import Optional

from config import (
    OLLAMA_BASE_URL,
    VISION_MODEL,
    FRAME_INTERVAL_SECONDS,
    MAX_SAMPLE_SECONDS,
)

def _edit_distance(a: str, b: str) -> int:
    """Simple Levenshtein distance for fuzzy artist dedup."""
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j] + (ca != cb), curr[-1] + 1, prev[j + 1] + 1))
        prev = curr
    return prev[-1]

def _fuzzy_artist_key(artist_key: str, existing_keys: list) -> str:
    """Return existing key if within edit distance 2, else return artist_key."""
    for key in existing_keys:
        if _edit_distance(artist_key, key) <= 2:
            return key
    return artist_key

VISION_PROMPT = (
    "This is a frame from an Instagram music reel. "
    "Extract any artist name and track/song title visible as text overlay. "
    'Respond ONLY with JSON: {"artist": "...", "track": "..."}. '
    "If none visible, use null."
)


def extract_frames(video_path: str, frames_dir: str, interval: int = FRAME_INTERVAL_SECONDS) -> list[int]:
    """
    Extract frames at fixed intervals using ffmpeg.
    Returns list of timestamps (seconds) for which frames were successfully extracted.
    """
    timestamps = list(range(interval, MAX_SAMPLE_SECONDS + 1, interval))
    extracted = []
    for ts in timestamps:
        frame_path = os.path.join(frames_dir, f"frame_{ts}.jpg")
        result = subprocess.run([
            "ffmpeg", "-ss", str(ts), "-i", video_path,
            "-frames:v", "1", "-q:v", "2", frame_path, "-y", "-loglevel", "quiet"
        ])
        if os.path.exists(frame_path):
            extracted.append(ts)
    return extracted


def vision_read_frame(frame_path: str) -> dict:
    """
    Run Gemma4 vision on a single frame.
    Returns {"artist": str|None, "track": str|None}
    """
    with open(frame_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    response = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json={
        "model": VISION_MODEL,
        "stream": False,
        "messages": [{
            "role": "user",
            "content": VISION_PROMPT,
            "images": [img_b64]
        }]
    }, timeout=30)

    content = response.json()["message"]["content"].strip()
    # Strip markdown fences
    content = re.sub(r"^```[a-z]*\n?", "", content)
    content = re.sub(r"\n?```$", "", content).strip()
    # Extract JSON object
    m = re.search(r'\{.*\}', content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {"artist": None, "track": None}


def identify_tracks_from_video(video_path: str) -> list[dict]:
    """
    Sample frames from video and extract all unique tracks found.

    Deduplication rules:
    - Same artist appearing multiple times -> keep the last result
      (track card at e.g. 18s beats album card at 16s)
    - Minimum track name length: 2 chars
    - Maximum track name length: 80 chars (longer = likely not a track title)

    Returns list of dicts: [{artist, track, timestamp_found}]
    """
    frames_dir = tempfile.mkdtemp()
    timestamps = extract_frames(video_path, frames_dir)

    tracks = {}  # keyed by normalized artist name

    for ts in timestamps:
        frame_path = os.path.join(frames_dir, f"frame_{ts}.jpg")
        result = vision_read_frame(frame_path)

        artist = result.get("artist")
        track = result.get("track")

        if not artist or not track:
            continue
        if len(track) < 2 or len(track) > 80:
            continue
        if len(artist) > 60:
            continue

        # Normalize artist key for dedup (lowercase, strip punctuation)
        artist_key = re.sub(r'[^a-z0-9]', '', artist.lower())
        # Always overwrite -- later frame (track card) beats earlier (album card)
        tracks[artist_key] = {
            "artist": artist,
            "track": track,
            "timestamp_found": ts,
            "id_method": "vision",
            "confidence": "high",
        }

    return list(tracks.values())