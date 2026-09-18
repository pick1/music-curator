"""
Instagram Reel extraction using yt-dlp.
"""

import os
import tempfile
import shutil
from typing import Optional

import yt_dlp

from config import YDL_OPTS_BASE


def _get_ydl_opts_base(cookiefile: Optional[str] = None) -> dict:
    """Get base yt-dlp options with cookie handling."""
    opts = YDL_OPTS_BASE.copy()
    if cookiefile and os.path.exists(cookiefile):
        opts["cookiefile"] = cookiefile
        # Remove cookiesfrombrowser when using cookiefile
        opts.pop("cookiesfrombrowser", None)
    return opts


def extract_reel_info(url: str, cookiefile: Optional[str] = None) -> dict:
    """
    Extract metadata from an Instagram Reel without downloading.

    Returns:
        dict with keys: title, description, uploader, audio_url, webpage_url, id
    """
    opts = _get_ydl_opts_base(cookiefile)
    opts.update({
        "skip_download": True,
        "extract_flat": False,
    })

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    return {
        "title": info.get("title", ""),
        "description": info.get("description", ""),
        "uploader": info.get("uploader", ""),
        "audio_url": info.get("url"),
        "webpage_url": info.get("webpage_url", url),
        "id": info.get("id", ""),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "timestamp": info.get("timestamp"),
    }


def download_reel_audio(url: str, out_dir: str, cookiefile: Optional[str] = None) -> str:
    """
    Download the audio from an Instagram Reel as MP3.

    Args:
        url: Instagram Reel URL
        out_dir: Directory to save the MP3
        cookiefile: Optional path to cookies.txt file

    Returns:
        Path to the downloaded MP3 file
    """
    os.makedirs(out_dir, exist_ok=True)

    opts = _get_ydl_opts_base(cookiefile)
    opts.update({
        "format": "bestaudio/best",
        "outtmpl": os.path.join(out_dir, "%(id)s.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "keepvideo": False,
    })

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    # Find the downloaded MP3 file
    video_id = info.get("id", "")
    mp3_path = os.path.join(out_dir, f"{video_id}.mp3")

    import glob
    mp3_files = glob.glob(os.path.join(out_dir, "*.mp3"))
    if mp3_files:
        return mp3_files[0]
    if os.path.exists(mp3_path):
        return mp3_path
    raise FileNotFoundError(f"Downloaded MP3 not found for {video_id}")


def extract_with_fallback(url: str) -> dict:
    """
    Try to extract reel info with multiple cookie strategies.

    Strategy order:
    1. Chrome cookies (default)
    2. Firefox cookies
    3. Cookies file (instagram_cookies.txt in cwd or ~/.config)
    """
    errors = []

    # Try Chrome cookies
    try:
        return extract_reel_info(url)
    except Exception as e:
        errors.append(("chrome", str(e)))

    # Try Firefox cookies
    try:
        opts = YDL_OPTS_BASE.copy()
        opts["cookiesfrombrowser"] = ("firefox",)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return {
            "title": info.get("title", ""),
            "description": info.get("description", ""),
            "uploader": info.get("uploader", ""),
            "audio_url": info.get("url"),
            "webpage_url": info.get("webpage_url", url),
            "id": info.get("id", ""),
        }
    except Exception as e:
        errors.append(("firefox", str(e)))

    # Try cookie file
    cookie_paths = [
        "instagram_cookies.txt",
        os.path.expanduser("~/.config/instagram_cookies.txt"),
        os.path.expanduser("~/instagram_cookies.txt"),
    ]
    for cookie_path in cookie_paths:
        if os.path.exists(cookie_path):
            try:
                return extract_reel_info(url, cookiefile=cookie_path)
            except Exception as e:
                errors.append((f"cookiefile:{cookie_path}", str(e)))

    # All failed
    raise RuntimeError(
        f"Failed to extract Instagram Reel info. Tried: {', '.join(e[0] for e in errors)}. "
        f"Last error: {errors[-1][1] if errors else 'unknown'}"
    )


def download_audio_with_fallback(url: str, out_dir: str) -> str:
    """
    Download audio with multiple cookie strategies.
    """
    errors = []

    # Try Chrome cookies
    try:
        return download_reel_audio(url, out_dir)
    except Exception as e:
        errors.append(("chrome", str(e)))

    # Try Firefox cookies
    try:
        opts = YDL_OPTS_BASE.copy()
        opts["cookiesfrombrowser"] = ("firefox",)
        opts.update({
            "format": "bestaudio/best",
            "outtmpl": os.path.join(out_dir, "%(id)s.%(ext)s"),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "keepvideo": False,
        })
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        video_id = info.get("id", "")
        mp3_path = os.path.join(out_dir, f"{video_id}.mp3")
        if os.path.exists(mp3_path):
            return mp3_path
    except Exception as e:
        errors.append(("firefox", str(e)))

    # Try cookie file
    cookie_paths = [
        "instagram_cookies.txt",
        os.path.expanduser("~/.config/instagram_cookies.txt"),
        os.path.expanduser("~/instagram_cookies.txt"),
    ]
    for cookie_path in cookie_paths:
        if os.path.exists(cookie_path):
            try:
                return download_reel_audio(url, out_dir, cookiefile=cookie_path)
            except Exception as e:
                errors.append((f"cookiefile:{cookie_path}", str(e)))

    raise RuntimeError(
        f"Failed to download Instagram Reel audio. Tried: {', '.join(e[0] for e in errors)}. "
        f"Last error: {errors[-1][1] if errors else 'unknown'}"
    )


def download_reel_video(url: str, out_dir: str, cookiefile: Optional[str] = None) -> str:
    """
    Download full video (smallest quality) for frame extraction.

    Args:
        url: Instagram Reel URL
        out_dir: Directory to save the video
        cookiefile: Optional path to cookies.txt file

    Returns:
        Path to the downloaded MP4 file
    """
    os.makedirs(out_dir, exist_ok=True)

    opts = _get_ydl_opts_base(cookiefile)
    opts.update({
        "format": "worst[ext=mp4]/worst",
        "outtmpl": os.path.join(out_dir, "%(id)s.%(ext)s"),
        "keepvideo": True,
        "skip_download": False,  # override base config
    })

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    # Find the downloaded MP4 file
    video_id = info.get("id", "")
    mp4_path = os.path.join(out_dir, f"{video_id}.mp4")

    import glob
    mp4_files = glob.glob(os.path.join(out_dir, "*.mp4"))
    if mp4_files:
        return mp4_files[0]
    if os.path.exists(mp4_path):
        return mp4_path
    raise FileNotFoundError(f"Downloaded MP4 not found for {video_id}")


# Convenience function for use in pipeline
def process_reel(url: str, download_audio: bool = False) -> dict:
    """
    Process an Instagram Reel URL and return metadata.
    Optionally download audio for fingerprinting.

    Returns:
        dict with info keys plus optional 'audio_path'
    """
    info = extract_with_fallback(url)

    if download_audio:
        with tempfile.mkdtemp(prefix="music_curator_") as tmpdir:
            try:
                audio_path = download_audio_with_fallback(url, tmpdir)
                info["audio_path"] = audio_path
                info["audio_tmpdir"] = tmpdir  # caller responsible for cleanup
            except Exception as e:
                info["audio_error"] = str(e)
                shutil.rmtree(tmpdir, ignore_errors=True)

    return info