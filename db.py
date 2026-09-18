"""
SQLite persistence layer for Music Curator.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

from config import DB_PATH


def get_conn() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    conn = get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tracks (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                captured_at     TEXT NOT NULL,
                source_url      TEXT NOT NULL,
                artist          TEXT,
                track           TEXT,
                album           TEXT,
                id_method       TEXT,
                spotify_found   INTEGER NOT NULL DEFAULT 0,
                spotify_track_id TEXT,
                spotify_uri     TEXT,
                spotify_genres  TEXT,
                genre_slug      TEXT,
                genre_source    TEXT,
                genre_confidence TEXT,
                playlist_id     TEXT,
                added_to_spotify INTEGER NOT NULL DEFAULT 0,
                flagged         INTEGER NOT NULL DEFAULT 0,
                flag_reason     TEXT,
                notes           TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS playlists (
                genre_slug      TEXT PRIMARY KEY,
                playlist_id     TEXT NOT NULL,
                playlist_name   TEXT NOT NULL,
                created_at      TEXT NOT NULL
            )
        """)
        # Index for faster lookups
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_source_url ON tracks(source_url)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_genre_slug ON tracks(genre_slug)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_flagged ON tracks(flagged)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_captured_at ON tracks(captured_at)")
        conn.commit()
    finally:
        conn.close()


def insert_track(record: dict) -> int:
    """
    Insert a new track record.
    Returns the row ID.
    """
    conn = get_conn()
    try:
        # Convert list/dict fields to JSON strings
        spotify_genres = record.get("spotify_genres")
        if isinstance(spotify_genres, (list, dict)):
            record = {**record, "spotify_genres": json.dumps(spotify_genres)}

        # Ensure captured_at is set
        if "captured_at" not in record:
            record["captured_at"] = datetime.utcnow().isoformat() + "Z"

        columns = ", ".join(record.keys())
        placeholders = ", ".join("?" * len(record))
        values = tuple(record.values())

        cursor = conn.execute(
            f"INSERT INTO tracks ({columns}) VALUES ({placeholders})",
            values
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def update_track(track_id: int, **kwargs) -> None:
    """Partial update of a track record."""
    if not kwargs:
        return

    # Convert list/dict fields to JSON strings
    if "spotify_genres" in kwargs and isinstance(kwargs["spotify_genres"], (list, dict)):
        kwargs["spotify_genres"] = json.dumps(kwargs["spotify_genres"])

    conn = get_conn()
    try:
        set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = tuple(kwargs.values()) + (track_id,)
        conn.execute(
            f"UPDATE tracks SET {set_clause} WHERE id = ?",
            values
        )
        conn.commit()
    finally:
        conn.close()


def get_track(track_id: int) -> Optional[dict]:
    """Get a single track by ID."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_track_by_url(source_url: str) -> Optional[dict]:
    """Get a track by source URL (for dedup)."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM tracks WHERE source_url = ?", (source_url,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_recent(n: int = 50) -> list[dict]:
    """Get the N most recent tracks."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM tracks ORDER BY captured_at DESC LIMIT ?",
            (n,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_flagged() -> list[dict]:
    """Get all flagged tracks."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM tracks WHERE flagged = 1 ORDER BY captured_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_tracks_by_genre(genre_slug: str, limit: int = 100) -> list[dict]:
    """Get tracks filtered by genre slug."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM tracks WHERE genre_slug = ? ORDER BY captured_at DESC LIMIT ?",
            (genre_slug, limit)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_all_tracks() -> list[dict]:
    """Get all tracks (for stats)."""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM tracks ORDER BY captured_at DESC").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# Playlist table operations
def upsert_playlist(genre_slug: str, playlist_id: str, playlist_name: str) -> None:
    """Insert or update a playlist mapping."""
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO playlists (genre_slug, playlist_id, playlist_name, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(genre_slug) DO UPDATE SET
                playlist_id = excluded.playlist_id,
                playlist_name = excluded.playlist_name
        """, (genre_slug, playlist_id, playlist_name, datetime.utcnow().isoformat() + "Z"))
        conn.commit()
    finally:
        conn.close()


def get_playlist(genre_slug: str) -> Optional[dict]:
    """Get playlist mapping by genre slug."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM playlists WHERE genre_slug = ?",
            (genre_slug,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_all_playlists() -> list[dict]:
    """Get all playlist mappings."""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM playlists").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# Stats
def get_stats() -> dict:
    """Get aggregate statistics."""
    conn = get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        added = conn.execute("SELECT COUNT(*) FROM tracks WHERE added_to_spotify = 1").fetchone()[0]
        flagged = conn.execute("SELECT COUNT(*) FROM tracks WHERE flagged = 1").fetchone()[0]
        spotify_found = conn.execute("SELECT COUNT(*) FROM tracks WHERE spotify_found = 1").fetchone()[0]

        # Genre breakdown
        genre_rows = conn.execute(
            "SELECT genre_slug, COUNT(*) FROM tracks WHERE genre_slug IS NOT NULL GROUP BY genre_slug"
        ).fetchall()
        genre_counts = {row[0]: row[1] for row in genre_rows}

        # ID method breakdown
        method_rows = conn.execute(
            "SELECT id_method, COUNT(*) FROM tracks WHERE id_method IS NOT NULL GROUP BY id_method"
        ).fetchall()
        method_counts = {row[0]: row[1] for row in method_rows}

        return {
            "total": total,
            "added_to_spotify": added,
            "flagged": flagged,
            "spotify_found": spotify_found,
            "by_genre": genre_counts,
            "by_id_method": method_counts,
        }
    finally:
        conn.close()

def delete_track(track_id: int) -> bool:
    """Delete a track by ID."""
    conn = get_conn()
    try:
        cursor = conn.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def find_duplicates() -> list[dict]:
    """Find duplicate tracks by artist+track name, returning all but the earliest."""
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT * FROM tracks WHERE id NOT IN (
                SELECT MIN(id) FROM tracks
                WHERE artist IS NOT NULL AND track IS NOT NULL
                GROUP BY LOWER(artist), LOWER(track)
            )
            AND artist IS NOT NULL AND track IS NOT NULL
            ORDER BY artist, track
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def track_already_exists(artist: str, track: str) -> Optional[dict]:
    """
    Check if a track by this artist already exists in the DB.
    Returns the existing row dict or None.
    """
    if not artist or not track:
        return None
    conn = get_conn()
    try:
        row = conn.execute("""
            SELECT * FROM tracks
            WHERE LOWER(artist) = LOWER(?)
            AND LOWER(track) = LOWER(?)
            LIMIT 1
        """, (artist.strip(), track.strip())).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
