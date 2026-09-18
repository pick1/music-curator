"""
Spotify Web API client using spotipy.

Handles OAuth2 Authorization Code flow, track search, artist genres,
and playlist management.
"""

import os
import json
from pathlib import Path
from typing import Optional

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from config import (
    SPOTIFY_CLIENT_ID,
    SPOTIFY_CLIENT_SECRET,
    SPOTIFY_REDIRECT_URI,
    SPOTIFY_SCOPES,
    PLAYLIST_NAME_TEMPLATE,
)
from db import get_playlist, upsert_playlist


# Cache file for OAuth tokens
CACHE_PATH = Path(__file__).with_name(".spotify_cache")


def _get_auth_manager() -> SpotifyOAuth:
    """Create SpotifyOAuth manager."""
    return SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope=SPOTIFY_SCOPES,
        cache_path=str(CACHE_PATH),
        open_browser=False,
    )


def get_spotify_client() -> spotipy.Spotify:
    """Get an authenticated Spotify client."""
    auth_manager = _get_auth_manager()
    return spotipy.Spotify(auth_manager=auth_manager)


def get_auth_url() -> str:
    """Get the authorization URL for initial OAuth flow."""
    auth_manager = _get_auth_manager()
    return auth_manager.get_authorize_url()


def search_track(artist: str, track: str) -> Optional[dict]:
    """
    Search for a track on Spotify.

    Args:
        artist: Artist name
        track: Track name

    Returns:
        Spotify track object or None if not found
    """
    sp = get_spotify_client()

    # Build query - try exact match first
    query = f'track:"{track}" artist:"{artist}"'
    results = sp.search(q=query, type="track", limit=5)

    tracks = results.get("tracks", {}).get("items", [])
    if tracks:
        # Return the first (most relevant) result
        return tracks[0]

    # Fallback: looser search
    query = f"{track} {artist}"
    results = sp.search(q=query, type="track", limit=10)
    tracks = results.get("tracks", {}).get("items", [])

    if tracks:
        # Try to find best match by comparing artist names
        for t in tracks:
            track_artists = [a["name"].lower() for a in t["artists"]]
            if artist.lower() in track_artists:
                return t
        # If no artist match, return first result
        return tracks[0]

    return None


def get_artist_genres(artist_id: str) -> list[str]:
    """
    Get genre tags for an artist.

    Args:
        artist_id: Spotify artist ID

    Returns:
        List of genre strings
    """
    sp = get_spotify_client()
    try:
        artist = sp.artist(artist_id)
        return artist.get("genres", [])
    except Exception:
        return []


def get_track_by_id(track_id: str) -> Optional[dict]:
    """Get full track object by Spotify track ID."""
    sp = get_spotify_client()
    try:
        return sp.track(track_id)
    except Exception:
        return None


def get_or_create_playlist(genre_slug: str) -> Optional[str]:
    """
    Get existing playlist ID for genre or create new one.

    Args:
        genre_slug: Genre taxonomy slug (e.g., 'electronic')

    Returns:
        Spotify playlist ID or None on failure
    """
    from config import GENRE_TAXONOMY

    # Check local DB first
    existing = get_playlist(genre_slug)
    if existing:
        return existing["playlist_id"]

    # Not in local DB, check Spotify for existing playlist
    sp = get_spotify_client()
    user_id = sp.current_user()["id"]
    display_name = GENRE_TAXONOMY.get(genre_slug, genre_slug)
    playlist_name = PLAYLIST_NAME_TEMPLATE.format(display_name=display_name)

    # Search user's playlists
    playlists = sp.current_user_playlists(limit=50)
    while playlists:
        for pl in playlists["items"]:
            if pl["name"] == playlist_name:
                # Found it, cache locally
                upsert_playlist(genre_slug, pl["id"], playlist_name)
                return pl["id"]
        if playlists["next"]:
            playlists = sp.next(playlists)
        else:
            break

    # Create new playlist
    try:
        playlist = sp._post("me/playlists", payload={
            "name": playlist_name,
            "public": False,
            "description": f"Auto-curated {display_name} tracks from Instagram Reels",
        })
        playlist_id = playlist["id"]
        upsert_playlist(genre_slug, playlist_id, playlist_name)
        return playlist_id
    except Exception as e:
        print(f"Failed to create playlist for {genre_slug}: {e}")
        return None


def add_to_instagems(track_uri: str) -> bool:
    """Mirror every track to instaGems playlist."""
    from config import INSTAGEMS_PLAYLIST_ID
    return add_to_playlist(INSTAGEMS_PLAYLIST_ID, track_uri)


def add_to_playlist(playlist_id: str, track_uri: str) -> bool:
    """
    Add a track to a playlist (deduplicates).

    Args:
        playlist_id: Spotify playlist ID
        track_uri: Spotify track URI (spotify:track:...)

    Returns:
        True if added (or already present), False on error
    """
    sp = get_spotify_client()

    # Check if track already in playlist
    try:
        # Get playlist tracks in batches
        offset = 0
        limit = 100
        while True:
            results = sp.playlist_items(
                playlist_id,
                fields="items.track.uri,total,next",
                limit=limit,
                offset=offset,
            )
            for item in results["items"]:
                if item["track"] and item["track"]["uri"] == track_uri:
                    return True  # Already in playlist
            if not results["next"]:
                break
            offset += limit
    except Exception:
        # If we can't check, try to add anyway (API will handle dedup)
        pass

    # Add track
    try:
        sp.playlist_add_items(playlist_id, [track_uri])
        return True
    except Exception as e:
        print(f"Failed to add track to playlist: {e}")
        return False


def get_playlist_tracks(playlist_id: str, limit: int = 100) -> list[dict]:
    """Get tracks from a playlist."""
    sp = get_spotify_client()
    tracks = []
    try:
        results = sp.playlist_items(playlist_id, limit=limit)
        tracks.extend(results["items"])
        while results["next"] and len(tracks) < limit:
            results = sp.next(results)
            tracks.extend(results["items"])
    except Exception:
        pass
    return tracks[:limit]


def remove_from_playlist(playlist_id: str, track_uri: str) -> bool:
    """Remove a track from a playlist."""
    sp = get_spotify_client()
    try:
        sp.playlist_remove_all_occurrences_of_items(playlist_id, [track_uri])
        return True
    except Exception:
        return False


# -----------------------------------------------------------------------------
# Helper for initial auth (run once to generate cache)
# -----------------------------------------------------------------------------

def run_initial_auth() -> None:
    """
    Run initial OAuth flow to generate token cache.
    Call this once during setup, then use the cached token.
    """
    print("Starting Spotify OAuth flow...")
    print(f"1. Open this URL in your browser:\n{get_auth_url()}")
    print("2. Authorize the application")
    print("3. Copy the FULL redirect URL (including http://localhost:8888/callback?code=...)")
    print("4. Paste it here:")

    redirect_url = input("> ").strip()

    # Extract code from redirect URL
    import urllib.parse
    parsed = urllib.parse.urlparse(redirect_url)
    code = urllib.parse.parse_qs(parsed.query).get("code", [None])[0]

    if not code:
        print("Error: No authorization code found in URL")
        return

    auth_manager = _get_auth_manager()
    token_info = auth_manager.get_access_token(code, as_dict=True)

    if token_info:
        print(f"Success! Token cached to {CACHE_PATH}")
    else:
        print("Failed to get access token")