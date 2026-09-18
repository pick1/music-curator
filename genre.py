"""
Genre classification for Music Curator.

Step 1: Map Spotify artist genre tags to taxonomy slugs
Step 2: If ambiguous/missing, use OpenRouter LLM to classify
"""

import os
import json
import re
from typing import Optional

from openai import OpenAI

from config import (
    GENRE_TAXONOMY,
    GENRE_SLUGS,
    SPOTIFY_GENRE_TO_SLUG,
    OPENROUTER_MODEL,
    OPENROUTER_BASE_URL,
)


def _map_spotify_genres(spotify_genres: list[str]) -> Optional[str]:
    """
    Map Spotify genre tags to our taxonomy slug.

    Returns:
        Single taxonomy slug if unambiguous match, None if ambiguous or no match
    """
    if not spotify_genres:
        return None

    matches = []
    for genre in spotify_genres:
        genre_lower = genre.lower().strip()
        if genre_lower in SPOTIFY_GENRE_TO_SLUG:
            matches.append(SPOTIFY_GENRE_TO_SLUG[genre_lower])

    if not matches:
        return None

    # If all matches point to same slug, high confidence
    unique_matches = set(matches)
    if len(unique_matches) == 1:
        return list(unique_matches)[0]

    # Multiple conflicting slugs - ambiguous
    return None


# -----------------------------------------------------------------------------
# OpenRouter LLM Classification
# -----------------------------------------------------------------------------

def _build_classification_prompt(
    artist: str,
    track: str,
    album: Optional[str],
    spotify_genres: list[str],
    caption: str
) -> str:
    """Build the classification prompt for OpenRouter."""
    genre_list = ", ".join(f'"{slug}"' for slug in GENRE_SLUGS)

    prompt = f"""You are a music genre classifier. Given the following track info, classify it into exactly one of these genre slugs: [{genre_list}].

Respond ONLY with a JSON object:
{{
  "genre_slug": "...",
  "confidence": "high"|"low",
  "reasoning": "..."
}}

Artist: {artist or "Unknown"}
Track: {track or "Unknown"}
Album: {album or "Unknown"}
Spotify genre tags: {json.dumps(spotify_genres) if spotify_genres else "[]"}
Instagram caption: {caption or "Not available"}"""
    return prompt


def classify_with_openrouter(
    artist: str,
    track: str,
    album: Optional[str],
    spotify_genres: list[str],
    caption: str
) -> dict:
    """
    Classify genre using OpenRouter API.

    Returns:
        dict with genre_slug, confidence, reasoning, genre_source
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return {
            "genre_slug": "other",
            "genre_source": "openrouter",
            "genre_confidence": "low",
            "reasoning": "OPENROUTER_API_KEY not configured",
        }

    client = OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=api_key,
    )

    prompt = _build_classification_prompt(artist, track, album, spotify_genres, caption)

    try:
        response = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1000,  # Nemotron uses reasoning tokens before output
        )

        raw = response.choices[0].message.content
        if not raw:
            raise ValueError("Model returned empty content")
        raw = raw.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw).strip()
        # Extract first JSON object if extra text present
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        raw = m.group(0) if m else raw
        result = json.loads(raw)

        # Validate response
        genre_slug = result.get("genre_slug", "other")
        confidence = result.get("confidence", "low")
        reasoning = result.get("reasoning", "")

        if genre_slug not in GENRE_SLUGS:
            genre_slug = "other"
            confidence = "low"

        return {
            "genre_slug": genre_slug,
            "genre_source": "openrouter",
            "genre_confidence": confidence,
            "reasoning": reasoning,
        }

    except Exception as e:
        return {
            "genre_slug": "other",
            "genre_source": "openrouter",
            "genre_confidence": "low",
            "reasoning": f"OpenRouter call failed: {e}",
        }


# -----------------------------------------------------------------------------
# Main Classification Function
# -----------------------------------------------------------------------------

def classify_genre(
    artist: str,
    track: str,
    album: Optional[str],
    spotify_genres: list[str],
    caption: str
) -> dict:
    """
    Classify track into genre taxonomy.

    Priority:
    1. Direct Spotify genre tag mapping (high confidence)
    2. OpenRouter LLM classification (medium/low confidence)
    3. Default to 'other' (manual review)

    Returns:
        dict with genre_slug, genre_source, genre_confidence, reasoning
    """
    # Step 1: Try Spotify genre mapping
    mapped_slug = _map_spotify_genres(spotify_genres)
    if mapped_slug:
        return {
            "genre_slug": mapped_slug,
            "genre_source": "spotify",
            "genre_confidence": "high",
            "reasoning": f"Mapped from Spotify genre tags: {spotify_genres}",
        }

    # Step 2: OpenRouter fallback
    result = classify_with_openrouter(artist, track, album, spotify_genres, caption)

    # If OpenRouter returns 'other' or low confidence, flag for review
    if result["genre_slug"] == "other" or result["genre_confidence"] == "low":
        result["flag_for_review"] = True
        result["reasoning"] = result.get("reasoning", "") + " [FLAGGED FOR MANUAL REVIEW]"

    return result


# -----------------------------------------------------------------------------
# Utility: Get display name for genre slug
# -----------------------------------------------------------------------------

def get_genre_display(genre_slug: str) -> str:
    """Get display name for genre slug."""
    return GENRE_TAXONOMY.get(genre_slug, genre_slug)