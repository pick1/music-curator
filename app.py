"""
Music Curator — Streamlit UI

Three tabs:
1. Add Track: Paste Instagram Reel URL → process pipeline
2. Library: View recent tracks, filter by genre
3. Flagged: Review tracks needing manual intervention
"""

import streamlit as st
import time
from datetime import datetime
from typing import Optional

# Import our modules
from reel_extractor import extract_reel_info, download_reel_audio, download_audio_with_fallback, download_reel_video
from identifier import identify_track, is_multi_track_caption, looks_like_instagram_handle
from genre import classify_genre, get_genre_display
from spotify_client import (
    get_spotify_client,
    search_track,
    get_artist_genres,
    get_or_create_playlist,
    add_to_playlist,
    add_to_instagems,
)
from db import (
    track_already_exists,
    delete_track,
    find_duplicates,
    init_db,
    insert_track,
    update_track,
    get_recent,
    get_flagged,
    get_stats,
)
from config import validate_config, GENRE_SLUGS, GENRE_TAXONOMY, USER_MIRROR_PLAYLISTS
from vision_identifier import identify_tracks_from_video


# -----------------------------------------------------------------------------
# Page Configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="DISCO — Music Curator",
    page_icon="static/disco_favicon.svg",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for dark theme accents
st.markdown("""
<style>
    .stProgress > div > div > div > div {
        background-color: #00ff88;
    }
    .success-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #004400;
        border: 1px solid #00ff88;
    }
    .warning-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #444400;
        border: 1px solid #ffaa00;
    }
    .error-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #440000;
        border: 1px solid #ff4444;
    }
    .info-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #000044;
        border: 1px solid #0088ff;
    }
</style>
""", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# Initialize
# -----------------------------------------------------------------------------
def init_app():
    """Initialize app state and database."""
    if "initialized" not in st.session_state:
        # Check config
        missing = validate_config()
        if missing:
            st.error(f"Missing environment variables: {', '.join(missing)}")
            st.info("Please set them in .env file and restart")
            st.stop()

        # Initialize database
        init_db()
        st.session_state.initialized = True


init_app()


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------
def process_reel_pipeline(url: str) -> dict:
    """
    Run the full pipeline for an Instagram Reel URL.

    Returns result dict with keys:
    - success: bool
    - data: dict with track info and processing results
    - error: str (if success=False)
    """
    try:
        # Step 1: Extract reel info + download audio for fingerprinting
        with st.status("Extracting reel info...", expanded=True) as status:
            info = extract_reel_info(url)
            import tempfile, os
            tmpdir = tempfile.mkdtemp()
            try:
                import yt_dlp, glob
                ydl_opts = {
                    "cookiesfrombrowser": ("chrome",),
                    "format": "bestaudio/best",
                    "outtmpl": os.path.join(tmpdir, "%(id)s.%(ext)s"),
                    "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
                    "quiet": True,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.extract_info(url, download=True)
                mp3_files = glob.glob(os.path.join(tmpdir, "*.mp3"))
                audio_path = mp3_files[0] if mp3_files else None
                print(f"Audio path: {audio_path}, files: {os.listdir(tmpdir)}")
            except Exception as e:
                print(f"Audio download failed: {e}")
                audio_path = None
            status.update(label="Extracting reel info...", state="complete")

        # Step 2: Identify track (check for multi-track)
        with st.status("Identifying track...", expanded=True) as status:
            identification = identify_track(info, audio_path)
            # Also trigger vision if caption parse returned an IG handle as artist
            if (not identification.get("multi_track")
                    and identification.get("id_method") == "caption"
                    and looks_like_instagram_handle(identification.get("artist", ""))):
                identification["multi_track"] = True

            if identification.get("multi_track"):
                status.update(label="Multi-track reel detected — scanning frames...", state="complete")
                # Download video and run vision extraction
                video_path = download_reel_video(url, tmpdir)
                tracks_found = identify_tracks_from_video(video_path)
                
                if not tracks_found:
                    # Cleanup temp files
                    if tmpdir and os.path.exists(tmpdir):
                        import shutil
                        shutil.rmtree(tmpdir, ignore_errors=True)
                    return {"success": False, "error": "No tracks identified from video frames"}
                
                status.update(label=f"Found {len(tracks_found)} tracks", state="complete")
                
                # Process each track through the normal pipeline
                results = []
                for track_info in tracks_found:
                    result = process_single_track(url, track_info, info)
                    results.append(result)
                
                # Cleanup temp files
                if tmpdir and os.path.exists(tmpdir):
                    import shutil
                    shutil.rmtree(tmpdir, ignore_errors=True)
                
                return {
                    "success": True,
                    "multi_track": True,
                    "results": results
                }
            
            # Single track processing (original logic)
            artist = identification.get("artist")
            track = identification.get("track")
            album = identification.get("album")
            id_method = identification.get("id_method")
            status.update(label="Identifying track...", state="complete")

        if not artist or not track:
            # Cleanup temp files
            if tmpdir and os.path.exists(tmpdir):
                import shutil
                shutil.rmtree(tmpdir, ignore_errors=True)
            return {
                "success": False,
                "error": f"Could not identify track: {identification.get('error', 'Unknown error')}",
                "partial_data": {
                    "source_url": url,
                    "captured_at": datetime.utcnow().isoformat() + "Z",
                    "identification": identification,
                    "extractor_info": info,
                }
            }

        # Dupe check
        existing = track_already_exists(artist, track)
        if existing:
            st.warning(f"⚠️ Already in library: **{track}** by {artist}")
            st.caption(f"Added {existing.get('captured_at', '')[:10]} · Playlist: {existing.get('genre_slug', 'unknown')}")
            return {"success": False, "duplicate": True, "existing": existing}

        # Step 3: Search Spotify
        with st.status("Searching Spotify...", expanded=True) as status:
            spotify_track = search_track(artist, track)
            spotify_found = spotify_track is not None
            spotify_track_id = spotify_track["id"] if spotify_track else None
            spotify_uri = spotify_track["uri"] if spotify_track else None
            status.update(label="Searching Spotify...", state="complete")

        # Step 4: Get artist genres if track found
        spotify_genres = []
        if spotify_found and spotify_track_id:
            # Get artist ID from track
            artist_id = spotify_track["artists"][0]["id"]
            spotify_genres = get_artist_genres(artist_id)

        # Step 5: Classify genre
        with st.status("Classifying genre...", expanded=True) as status:
            caption = info.get("description", "") + "\n" + info.get("title", "")
            genre_result = classify_genre(
                artist=artist,
                track=track,
                album=album,
                spotify_genres=spotify_genres,
                caption=caption,
            )
            genre_slug = genre_result["genre_slug"]
            genre_source = genre_result["genre_source"]
            genre_confidence = genre_result["genre_confidence"]
            reasoning = genre_result.get("reasoning", "")
            status.update(label="Classifying genre...", state="complete")

        # Step 6: Route to Spotify (unless flagged for review)
        playlist_id = None
        added_to_spotify = 0
        flagged = 0
        flag_reason = None

        if genre_slug == "other" or genre_confidence == "low":
            flagged = 1
            flag_reason = "Low confidence classification or 'other' genre"
        elif not spotify_found:
            flagged = 1
            flag_reason = "Track not found on Spotify"
        else:
            # Try to add to playlist
            playlist_id = get_or_create_playlist(genre_slug)
            if playlist_id:
                added_to_spotify = add_to_playlist(playlist_id, spotify_uri)
                if added_to_spotify:
                    add_to_instagems(spotify_uri)
                else:
                    flagged = 1
                    flag_reason = "Failed to add track to playlist"
            else:
                flagged = 1
                flag_reason = f"Could not get/create playlist for genre {genre_slug}"

        # Step 7: Persist to database
        track_record = {
            "source_url": url,
            "artist": artist,
            "track": track,
            "album": album,
            "id_method": id_method,
            "spotify_found": int(spotify_found),
            "spotify_track_id": spotify_track_id,
            "spotify_uri": spotify_uri,
            "spotify_genres": spotify_genres,
            "genre_slug": genre_slug,
            "genre_source": genre_source,
            "genre_confidence": genre_confidence,
            "playlist_id": playlist_id,
            "added_to_spotify": added_to_spotify,
            "flagged": flagged,
            "flag_reason": flag_reason,
            "notes": reasoning,  # Store LLM reasoning in notes
            "captured_at": datetime.utcnow().isoformat() + "Z",
        }

        track_id = insert_track(track_record)

        # Cleanup temp files
        if tmpdir and os.path.exists(tmpdir):
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

        return {
            "success": True,
            "data": {
                "track_id": track_id,
                "artist": artist,
                "track": track,
                "album": album,
                "genre_slug": genre_slug,
                "genre_display": get_genre_display(genre_slug),
                "genre_confidence": genre_confidence,
                "genre_source": genre_source,
                "reasoning": reasoning,
                "spotify_found": spotify_found,
                "spotify_track_id": spotify_track_id,
                "playlist_id": playlist_id,
                "added_to_spotify": added_to_spotify,
                "flagged": flagged,
                "flag_reason": flag_reason,
                "id_method": id_method,
                "captured_at": track_record["captured_at"],
            }
        }

    except Exception as e:
        # Cleanup temp files on error
        if 'tmpdir' in locals() and tmpdir and os.path.exists(tmpdir):
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
        return {
            "success": False,
            "error": str(e),
            "partial_data": locals().get("info", {})
        }


def process_single_track(source_url: str, track_info: dict, reel_info: dict) -> dict:
    """
    Run Spotify search -> genre classification -> DB insert for one identified track.
    Returns result dict (same shape as single-track pipeline result).
    """
    artist = track_info.get("artist")
    track = track_info.get("track")
    album = track_info.get("album")
    id_method = track_info.get("id_method", "vision")

    # Step 1: Search Spotify
    with st.status(f"Searching Spotify: {artist} - {track}...", expanded=True) as status:
        spotify_track = search_track(artist, track)
        spotify_found = spotify_track is not None
        spotify_track_id = spotify_track["id"] if spotify_track else None
        spotify_uri = spotify_track["uri"] if spotify_track else None
        status.update(label=f"Searching Spotify: {artist} - {track}...", state="complete")

    # Step 2: Get artist genres if track found
    spotify_genres = []
    if spotify_found and spotify_track_id:
        artist_id = spotify_track["artists"][0]["id"]
        spotify_genres = get_artist_genres(artist_id)

    # Step 3: Classify genre
    with st.status(f"Classifying genre: {artist} - {track}...", expanded=True) as status:
        caption = reel_info.get("description", "") + "\n" + reel_info.get("title", "")
        genre_result = classify_genre(
            artist=artist,
            track=track,
            album=album,
            spotify_genres=spotify_genres,
            caption=caption,
        )
        genre_slug = genre_result["genre_slug"]
        genre_source = genre_result["genre_source"]
        genre_confidence = genre_result["genre_confidence"]
        reasoning = genre_result.get("reasoning", "")
        status.update(label=f"Classifying genre: {artist} - {track}...", state="complete")

    # Step 4: Route to Spotify (unless flagged for review)
    playlist_id = None
    added_to_spotify = 0
    flagged = 0
    flag_reason = None

    # For multi-track reels, add all tracks to instaGems regardless of genre
    # Only flag if not found on Spotify
    if not spotify_found:
        flagged = 1
        flag_reason = "Track not found on Spotify"
    else:
        # Try to add to genre playlist
        playlist_id = get_or_create_playlist(genre_slug)
        if playlist_id:
            added_to_spotify = add_to_playlist(playlist_id, spotify_uri)
            if added_to_spotify:
                add_to_instagems(spotify_uri)
            else:
                flagged = 1
                flag_reason = "Failed to add track to playlist"
        else:
            flagged = 1
            flag_reason = f"Could not get/create playlist for genre {genre_slug}"

    # Step 5: Persist to database
    track_record = {
        "source_url": source_url,
        "artist": artist,
        "track": track,
        "album": album,
        "id_method": id_method,
        "spotify_found": int(spotify_found),
        "spotify_track_id": spotify_track_id,
        "spotify_uri": spotify_uri,
        "spotify_genres": spotify_genres,
        "genre_slug": genre_slug,
        "genre_source": genre_source,
        "genre_confidence": genre_confidence,
        "playlist_id": playlist_id,
        "added_to_spotify": added_to_spotify,
        "flagged": flagged,
        "flag_reason": flag_reason,
        "notes": reasoning,
        "captured_at": datetime.utcnow().isoformat() + "Z",
    }

    track_id = insert_track(track_record)

    return {
        "success": True,
        "data": {
            "track_id": track_id,
            "artist": artist,
            "track": track,
            "album": album,
            "genre_slug": genre_slug,
            "genre_display": get_genre_display(genre_slug),
            "genre_confidence": genre_confidence,
            "genre_source": genre_source,
            "reasoning": reasoning,
            "spotify_found": spotify_found,
            "spotify_track_id": spotify_track_id,
            "playlist_id": playlist_id,
            "added_to_spotify": added_to_spotify,
            "flagged": flagged,
            "flag_reason": flag_reason,
            "id_method": id_method,
            "captured_at": track_record["captured_at"],
            "timestamp_found": track_info.get("timestamp_found"),
        }
    }


def render_track_card(track: dict, show_actions: bool = False, context: str = 'default'):
    """Render a track as a card."""
    # Determine card color based on status
    if track.get("flagged"):
        border_color = "#ff4444"
        bg_color = "#440000"
    elif track.get("added_to_spotify"):
        border_color = "#00ff88"
        bg_color = "#004400"
    elif track.get("spotify_found"):
        border_color = "#ffaa00"
        bg_color = "#444400"
    else:
        border_color = "#888888"
        bg_color = "#222222"

    st.markdown(f"""
    <div style="
        border: 2px solid {border_color};
        border-radius: 0.5rem;
        padding: 1rem;
        margin: 0.5rem 0;
        background-color: {bg_color};
    ">
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([3, 1])

    with col1:
        st.markdown(f"**{track['track']}**")
        st.markdown(f"*by {track['artist']}*")
        if track.get("album"):
            st.caption(f"Album: {track['album']}")
        if track.get("source_url"):
            st.markdown(f"[📸 View Reel]({track['source_url']})", unsafe_allow_html=True)

        # Genre badge
        genre_display = track.get("genre_display") or get_genre_display(track.get("genre_slug", ""))
        confidence = track.get("genre_confidence", "unknown")
        confidence_color = {
            "high": "#00ff88",
            "low": "#ffaa00",
            "manual": "#ff4444",
        }.get(confidence, "#888888")
        st.markdown(
            f"<span style='background-color: {confidence_color}20; "
            f"color: {confidence_color}; padding: 0.2rem 0.5rem; "
            f"border-radius: 0.3rem; font-size: 0.8rem;'>"
            f"{genre_display} ({confidence})</span>",
            unsafe_allow_html=True,
        )

        if track.get("reasoning"):
            with st.expander("See classification reasoning"):
                st.write(track["reasoning"])

    with col2:
        if track.get("spotify_found"):
            st.success("✓ Spotify")
        else:
            st.error("✗ Not on Spotify")

        if track.get("added_to_spotify"):
            st.success("✓ Added")
        elif track.get("flagged"):
            st.warning("⚠ Flagged")
        else:
            st.info("○ Pending")

        if track.get("playlist_id"):
            st.caption(f"Playlist: {track.get('genre_slug', '')}")

    if show_actions:
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button(f"🗑 Delete", key=f"del_{context}_{track['id']}"):
                st.session_state[f"confirm_del_{track['id']}"] = True
            if st.session_state.get(f"confirm_del_{track['id']}"):
                st.warning(f"Delete **{track['track']}** by {track['artist']}?")
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if st.button("✅ Yes, delete", key=f"yes_del_{context}_{track['id']}"):
                        delete_track(track['id'])
                        st.session_state.pop(f"confirm_del_{track['id']}", None)
                        st.success("Deleted.")
                        st.rerun()
                with col_no:
                    if st.button("❌ Cancel", key=f"no_del_{context}_{track['id']}"):
                        st.session_state.pop(f"confirm_del_{track['id']}", None)
                        st.rerun()
        with col2:
            if track.get("flagged"):
                if st.button(f"✅ Resolve", key=f"resolve_{context}_{track['id']}"):
                    st.session_state[f"resolving_{track['id']}"] = True
            if st.session_state.get(f"resolving_{track['id']}"):
                genre_options = list(GENRE_TAXONOMY.keys())
                selected = st.selectbox(
                    "Select genre",
                    options=genre_options,
                    format_func=lambda s: GENRE_TAXONOMY[s],
                    key=f"genre_sel_{context}_{track['id']}"
                )
                col_confirm, col_cancel = st.columns(2)
                with col_confirm:
                    if st.button("✅ Confirm & Add", key=f"confirm_{context}_{track['id']}"):
                        from spotify_client import get_or_create_playlist, add_to_playlist, add_to_instagems
                        playlist_id = get_or_create_playlist(selected)
                        if playlist_id and track.get("spotify_track_id"):
                            uri = f"spotify:track:{track['spotify_track_id']}"
                            add_to_playlist(playlist_id, uri)
                            add_to_instagems(uri)
                            update_track(track['id'],
                                genre_slug=selected,
                                genre_confidence="manual",
                                genre_source="manual",
                                playlist_id=playlist_id,
                                added_to_spotify=1,
                                flagged=0,
                                flag_reason=None
                            )
                        st.session_state.pop(f"resolving_{track['id']}", None)
                        st.rerun()
                with col_cancel:
                    if st.button("❌ Cancel", key=f"cancel_res_{context}_{track['id']}"):
                        st.session_state.pop(f"resolving_{track['id']}", None)
                        st.rerun()
        with col3:
            if st.button(f"📝 Notes", key=f"notes_{context}_{track['id']}"):
                # TODO: show notes editor
                st.info("Notes editor not implemented yet")

    st.markdown("</div>", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# Main App
# -----------------------------------------------------------------------------
def main():

    # Login check
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if not st.session_state.logged_in:
        st.markdown(
            '<link href="https://fonts.googleapis.com/css2?family=Syne:wght@800&display=swap" rel="stylesheet">',
            unsafe_allow_html=True
        )
        st.markdown("""
            <style>
            .disco-header { font-family: 'Syne', sans-serif; font-size: 42px; font-weight: 800; color: #00ff88; letter-spacing: 0.18em; text-shadow: 0 0 30px rgba(0,255,136,0.4); margin-bottom: 0; line-height: 1; }
            .disco-sub { font-family: 'Syne', sans-serif; font-size: 13px; font-weight: 800; color: #888; letter-spacing: 0.25em; text-transform: uppercase; margin-top: 4px; }
            </style>
            <div style='text-align:center;margin-top:80px'>
            <div class='disco-header'>DISCO</div>
            </div>
        """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        import os
        from dotenv import load_dotenv
        load_dotenv('/home/dp/projects/music-curator/.env')
        _, col, _ = st.columns([1, 1, 1])
        with col:
            password = st.text_input("", type="password", placeholder="Enter password")
            if st.button("Enter", use_container_width=True):
                if password == os.getenv("DISCO_PASSWORD", ""):
                    st.session_state.logged_in = True
                    st.rerun()
                else:
                    st.error("Incorrect password")
        st.stop()  # Stop further execution if not logged in

    st.markdown(
        '<link href="https://fonts.googleapis.com/css2?family=Syne:wght@800&display=swap" rel="stylesheet">',
        unsafe_allow_html=True
    )
    st.markdown("""
        <style>
        .disco-header {
            font-family: 'Syne', sans-serif;
            font-size: 42px;
            font-weight: 800;
            color: #00ff88;
            letter-spacing: 0.18em;
            text-shadow: 0 0 30px rgba(0,255,136,0.4);
            margin-bottom: 0;
            line-height: 1;
        }
        .disco-sub {
            font-family: 'Syne', sans-serif;
            font-size: 13px;
            font-weight: 800;
            color: #888;
            letter-spacing: 0.25em;
            text-transform: uppercase;
            margin-top: 4px;
        }
        </style>
        <div class="disco-header">DISCO</div>
        <div class="disco-sub">Music Curator — Instagram → Spotify</div>
        <br>
    """, unsafe_allow_html=True)

    # User selector
    with st.sidebar:
        st.header("👤 User")
        active_user = st.radio("Who's adding?", ["dp", "mb"], horizontal=True)
        mirror_playlist_id = USER_MIRROR_PLAYLISTS.get(active_user, USER_MIRROR_PLAYLISTS["dp"])
        st.caption(f"Mirror: {'instaGems' if active_user == 'dp' else 'meggyInstaGems'}")
        st.markdown("---")
        st.caption("🎵 ID Chain")
        st.caption("1. Caption parse")
        st.caption("2. AcoustID (free)")
        st.caption("3. AudD (trial → Sep 24)")

    # Sidebar
    with st.sidebar:
        st.header("Dashboard")
        stats = get_stats()
        st.metric("Total Tracks", stats["total"])
        st.metric("Added to Spotify", stats["added_to_spotify"])
        st.metric("Flagged for Review", stats["flagged"])
        st.metric("Found on Spotify", stats["spotify_found"])

        if stats["by_genre"]:
            st.subheader("By Genre")
            for genre, count in stats["by_genre"].items():
                display = get_genre_display(genre)
                st.text(f"{display}: {count}")

    # Tabs
    tab1, tab2, tab3 = st.tabs(["➕ Add Track", "📚 Library", "🚩 Flagged"])

    # Tab 1: Add Track
    with tab1:
            st.subheader("Process Instagram Reel")
            url = st.text_input(
                "Paste Instagram Reel URL",
                placeholder="https://www.instagram.com/reel/XXXXXXX/",
                help="Paste a direct link to an Instagram Reel containing music"
            )

            if st.button("🔍 Process Reel", type="primary", disabled=not url):
                if url:
                    result = process_reel_pipeline(url)
                
                    if result["success"]:
                        if result.get("multi_track"):
                            st.success(f"✅ Multi-track reel processed successfully! Found {len(result['results'])} tracks")
                        
                            # Show summary card
                            st.markdown(
                                f"<div class='info-box'>"
                                f"<strong>Multi-track Reel Results</strong><br>"
                                f"Found {len(result['results'])} tracks in this Reel"
                                f"</div>",
                                unsafe_allow_html=True
                            )
                        
                            # Show each track result as a mini card
                            for i, track_result in enumerate(result["results"]):
                                with st.expander(f"Track {i+1}: {track_result['data']['track']} by {track_result['data']['artist']}", expanded=True):
                                    # Track info
                                    col1, col2 = st.columns([3, 1])
                                    with col1:
                                        st.markdown(f"**{track_result['data']['track']}**")
                                        st.markdown(f"*by {track_result['data']['artist']}*")
                                        if track_result['data'].get('album'):
                                            st.caption(f"Album: {track_result['data']['album']}")
                                    
                                        # Genre badge
                                        genre_display = track_result['data'].get('genre_display') or get_genre_display(track_result['data'].get('genre_slug', ''))
                                        confidence = track_result['data'].get('genre_confidence', 'unknown')
                                        confidence_color = {
                                            'high': '#00ff88',
                                            'low': '#ffaa00',
                                            'manual': '#ff4444',
                                        }.get(confidence, '#888888')
                                        st.markdown(
                                            f"<span style='background-color: {confidence_color}20; "
                                            f"color: {confidence_color}; padding: 0.2rem 0.5rem; "
                                            f"border-radius: 0.3rem; font-size: 0.8rem;'>"
                                            f"{genre_display} ({confidence})</span>",
                                            unsafe_allow_html=True,
                                        )
                                    
                                        if track_result['data'].get('reasoning'):
                                            with st.expander("See classification reasoning"):
                                                st.write(track_result['data']['reasoning'])
                                
                                    with col2:
                                        if track_result['data'].get('spotify_found'):
                                            st.success("✓ Spotify")
                                        else:
                                            st.error("✗ Not on Spotify")
                                    
                                        if track_result['data'].get('added_to_spotify'):
                                            st.success("✓ Added")
                                        elif track_result['data'].get('flagged'):
                                            st.warning("⚠ Flagged")
                                        else:
                                            st.info("○ Pending")
                                    
                                        if track_result['data'].get('playlist_id'):
                                            st.caption(f"Playlist: {track_result['data'].get('genre_slug', '')}")
                                
                                    # Detailed info
                                    with st.expander("View technical details"):
                                        st.json(track_result['data'])
                        else:
                            # Single track result (original logic)
                            data = result["data"]
                            st.success("✅ Track processed successfully!")
                        
                            # Result card
                            if data["flagged"]:
                                st.markdown(
                                    f"<div class='warning-box'>"
                                    f"<strong>Flagged for Review</strong><br>"
                                    f"Reason: {data['flag_reason']}</div>",
                                    unsafe_allow_html=True
                                )
                            elif data["added_to_spotify"]:
                                st.markdown(
                                    f"<div class='success-box'>"
                                    f"<strong>Added to Spotify!</strong><br>"
                                    f"Genre: {data['genre_display']} "
                                    f"(confidence: {data['genre_confidence']})</div>",
                                    unsafe_allow_html=True
                                )
                            else:
                                st.info("Track processed but not added to Spotify")

                            # Detailed info
                            with st.expander("View details"):
                                st.json(data)
                
                    elif result.get("duplicate"):
                        pass  # already shown above in pipeline
                    elif result.get("audd_quota_exhausted"):
                        st.error("❌ AudD quota exhausted")
                        st.warning("⚠️ AcoustID (free) is still active but has a smaller catalog. To restore full fingerprinting, renew your AudD plan at [audd.io](https://audd.io).")
                    else:
                        st.error(f"❌ Processing failed: {result.get('error', 'Unknown error')}")
                        if result.get("partial_data"):
                            with st.expander("View partial data (for debugging)"):
                                st.json(result["partial_data"])

    # Tab 2: Library
    with tab2:
        st.subheader("Track Library")
        
        # Filters
        col1, col2, col3 = st.columns(3)
        with col1:
            genre_filter = st.selectbox(
                "Filter by genre",
                options=["All"] + [get_genre_display(g) for g in GENRE_SLUGS],
                index=0
            )
        with col2:
            show_flagged = st.checkbox("Flagged only", value=False)
        with col3:
            limit = st.selectbox("Show", [10, 25, 50, 100], index=2)

        # Apply filters
        tracks = get_recent(n=100)  # Get more than we'll display for filtering
        
        if show_flagged:
            tracks = [t for t in tracks if t.get("flagged")]
        
        if genre_filter != "All":
            # Find slug for selected display name
            selected_slug = None
            for slug, display in GENRE_TAXONOMY.items():
                if display == genre_filter:
                    selected_slug = slug
                    break
            if selected_slug:
                tracks = [t for t in tracks if t.get("genre_slug") == selected_slug]

        tracks = tracks[:limit]  # Apply limit after filtering

        if not tracks:
            st.info("No tracks match the current filters")
        else:
            st.caption(f"Showing {len(tracks)} tracks")
            for track in tracks:
                render_track_card(track, show_actions=True, context='library')

        # Duplicates section
        dupes = find_duplicates()
        if dupes:
            st.markdown("---")
            st.subheader(f"🔁 Duplicates ({len(dupes)})")
            st.caption("These are duplicate entries — the earliest copy is kept.")
            for track in dupes:
                render_track_card(track, show_actions=True, context='dupe')

    # Tab 3: Flagged
    with tab3:
        st.subheader("Flagged Tracks")
        st.caption("Tracks requiring manual review")
        
        flagged_tracks = get_flagged()
        
        if not flagged_tracks:
            st.success("🎉 No flagged tracks!")
        else:
            st.warning(f"{len(flagged_tracks)} tracks need review")
            for track in flagged_tracks:
                render_track_card(track, show_actions=True, context='tab2')


if __name__ == "__main__":
    main()
