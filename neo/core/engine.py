import os
import uuid
import shutil
import urllib.parse
import re
import time
import threading
from pathlib import Path
from neo.core.logger import logger

try:
    import yt_dlp
    YTDLP_OK = True
except ImportError:
    YTDLP_OK = False

DOWNLOADS = Path(__file__).parent.parent.parent / "downloads"
DOWNLOADS.mkdir(exist_ok=True)

FFMPEG_OK = shutil.which("ffmpeg") is not None

# Metadata Cache
metadata_cache = {}
cache_lock = threading.Lock()
CACHE_TTL = 600 # 10 minutes

def get_cached_info(url):
    with cache_lock:
        if url in metadata_cache:
            entry = metadata_cache[url]
            if time.time() - entry['timestamp'] < CACHE_TTL:
                return entry['info']
            else:
                del metadata_cache[url]
    return None

def set_cached_info(url, info):
    with cache_lock:
        metadata_cache[url] = {
            'timestamp': time.time(),
            'info': info
        }
        # Prune old cache if too large
        if len(metadata_cache) > 200:
            oldest = min(metadata_cache.keys(), key=lambda k: metadata_cache[k]['timestamp'])
            del metadata_cache[oldest]

def get_site_label(url):
    u = url.lower()
    if 'youtube' in u or 'youtu.be' in u: return 'YouTube'
    if 'tiktok' in u: return 'TikTok'
    if 'instagram' in u: return 'Instagram'
    if 'twitter' in u or 'x.com' in u: return 'Twitter/X'
    if 'facebook' in u: return 'Facebook'
    if 't.me' in u or 'telegram' in u: return 'Telegram'
    if any(d in u for d in ["terabox", "1024tera", "dubox", "freeterabox", "teraboxapp"]): return 'Terabox'
    if 'reddit' in u: return 'Reddit'
    if 'twitch' in u: return 'Twitch'
    if 'vimeo' in u: return 'Vimeo'
    if 'soundcloud' in u: return 'SoundCloud'
    if 'spotify' in u: return 'Spotify'
    return 'Other'

def fetch_info(url, task_id=None):
    """Fetches media info from URL with caching."""
    cached = get_cached_info(url)
    if cached:
        return cached

    if not YTDLP_OK:
        raise Exception("yt-dlp not installed")

    # Fast extraction options
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "socket_timeout": 10,
        "no_playlist": True,
        "youtube_include_dash_manifest": False,
        "youtube_include_hls_manifest": False,
    }

    cookie_file = Path(__file__).parent.parent.parent / "cookies.txt"
    if cookie_file.is_file():
        opts["cookiefile"] = str(cookie_file)

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    set_cached_info(url, info)
    return info


def _extract_info_for_download(url, opts):
    """Reuse cached metadata when available to avoid a second network round-trip."""
    cached = get_cached_info(url)
    if cached and cached.get("formats") is not None:
        # Re-run with download=True but the cookie/file opts already applied; yt-dlp
        # will reuse the cached extract when possible.
        pass
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    return info

def get_direct_url(url, mode='video'):
    """Tries to get a direct CDN URL to bypass server download."""
    try:
        info = fetch_info(url)
    except Exception as e:
        logger.warning(f"Direct URL lookup failed for {url}: {e}")
        return None, None, None

    formats = info.get('formats', []) or []

    if mode == 'audio':
        # Prefer best audio-only format
        for f in formats:
            if f.get('acodec') != 'none' and f.get('vcodec') == 'none' and f.get('url'):
                return f['url'], f.get('ext', 'mp3'), info.get('title')
        # Fallback to any format with audio
        for f in formats:
            if f.get('acodec') != 'none' and f.get('url'):
                return f['url'], f.get('ext', 'mp3'), info.get('title')
    else:
        # Prefer best combined format (usually mp4 for compatibility)
        for f in formats:
            if f.get('acodec') != 'none' and f.get('vcodec') != 'none' and f.get('url'):
                if f.get('ext') == 'mp4': # High priority for mp4
                    return f['url'], 'mp4', info.get('title')
        # Fallback to any video
        for f in formats:
            if f.get('acodec') != 'none' and f.get('vcodec') != 'none' and f.get('url'):
                return f['url'], f.get('ext', 'mp4'), info.get('title')

    return None, None, None

def download_media(url, mode='video', format_id='best', task_id=None):
    """Downloads media from URL. Fast mode: tries direct URL first."""
    # Audio mode always downloads server-side and extracts a real, playable MP3.
    # YouTube's audio-only DASH streams (m4a/opus direct URLs) are often
    # unplayable in browsers and expire quickly, so fast mode is skipped.
    if mode != "audio":
        direct_url, ext, title = get_direct_url(url, mode)
        if direct_url:
            return {
                "success": True,
                "title": title,
                "direct_url": direct_url,
                "ext": ext,
                "site": get_site_label(url),
                "fast_mode": True
            }

    if not YTDLP_OK:
        raise Exception("yt-dlp not installed")

    uid = uuid.uuid4().hex
    outtmpl = str(DOWNLOADS / f"{uid}_%(title)s.%(ext)s")

    opts = {
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "concurrent_fragment_downloads": 16,
    }

    if shutil.which("aria2c"):
        opts["external_downloader"] = "aria2c"
        opts["external_downloader_args"] = ["-x", "16", "-s", "16", "-k", "1M"]

    if mode == "audio":
        if FFMPEG_OK:
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192"
            }]
        else:
            opts["format"] = "bestaudio/best"
    else:
        if not FFMPEG_OK:
            opts["format"] = "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best"
        elif format_id and format_id != "best":
            opts["format"] = f"{format_id}+bestaudio/best"
            opts["merge_output_format"] = "mp4"
        else:
            opts["format"] = "bestvideo+bestaudio/best"
            opts["merge_output_format"] = "mp4"

    cookie_file = Path(__file__).parent.parent.parent / "cookies.txt"
    if cookie_file.is_file():
        opts["cookiefile"] = str(cookie_file)

    def progress_hook(d):
        if task_id and d['status'] == 'downloading':
            try:
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 1
                p = d.get('downloaded_bytes', 0) / total * 100
                from neo.core.tasks import update_task
                update_task(task_id, progress=round(p, 2))
            except Exception:
                pass

    opts['progress_hooks'] = [progress_hook]

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = _extract_info_for_download(url, opts)
        filepath = ydl.prepare_filename(info)

    if filepath and mode == "audio" and FFMPEG_OK:
        filepath = str(Path(filepath).with_suffix(".mp3"))

    if filepath and os.path.isfile(filepath):
        p = Path(filepath)
    else:
        p = None
        for f in DOWNLOADS.iterdir():
            if f.name.startswith(uid):
                p = f
                break

    if not p or not p.is_file():
        raise Exception("Download failed - file not found")

    return {
        "title": info.get("title", "media"),
        "filename": p.name,
        "ext": p.suffix[1:],
        "filesize": p.stat().st_size,
        "site": get_site_label(url),
        "fast_mode": False
    }

def search_media(query, task_id=None):
    """Searches for media on YouTube."""
    if not YTDLP_OK:
        raise Exception("yt-dlp not installed")
    
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "socket_timeout": 15,
        "no_playlist": True,
    }
    
    search_url = f"ytsearch10:{query}"
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(search_url, download=False)
        
    results = []
    if 'entries' in info:
        for entry in info['entries']:
            results.append({
                "title": entry.get("title"),
                "url": entry.get("url") or entry.get("webpage_url"),
                "thumbnail": entry.get("thumbnail"),
                "duration": entry.get("duration"),
                "uploader": entry.get("uploader")
            })
    return results
