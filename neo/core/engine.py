import os
import uuid
import shutil
import urllib.parse
import re
import time
import threading
import tempfile
from pathlib import Path
from neo.core.logger import logger

try:
    import yt_dlp
    YTDLP_OK = True
except ImportError:
    YTDLP_OK = False

# Register the custom diskwala.com extractor so its URLs flow through the
# standard player like any other platform.
if YTDLP_OK:
    try:
        from neo.core.extractors.diskwala import register as _register_diskwala
        _register_diskwala()
    except Exception as _e:  # pragma: no cover - non-fatal
        logger.warning(f"Failed to register DiskWala extractor: {_e}")

DOWNLOADS = Path(__file__).parent.parent.parent / "downloads"
# Serverless (Vercel) has a read-only root; fall back to /tmp on mkdir failure.
try:
    DOWNLOADS.mkdir(exist_ok=True)
except OSError:
    DOWNLOADS = Path(tempfile.gettempdir()) / "downloads"
    DOWNLOADS.mkdir(exist_ok=True)

FFMPEG_OK = shutil.which("ffmpeg") is not None

# Metadata Cache
metadata_cache = {}
cache_lock = threading.Lock()
CACHE_TTL = 600 # 10 minutes

def _apply_cookies(opts, cookiefile=None):
    """Attach YouTube/age-restricted auth cookies to yt-dlp options.

    Priority: explicit `cookiefile` arg > YTDLP_COOKIES env var >
    cookies.txt at the project root. Env/serverless cookies are written to a
    temp file because yt-dlp's `cookiefile` option only accepts a path.
    """
    if cookiefile:
        opts["cookiefile"] = str(cookiefile)
        return opts
    env_cookies = os.environ.get("YTDLP_COOKIES", "").strip()
    if env_cookies:
        try:
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, prefix="neo_cookies_"
            )
            tmp.write(env_cookies)
            tmp.close()
            opts["cookiefile"] = tmp.name
            return opts
        except OSError:
            pass
    cookie_file = Path(__file__).parent.parent.parent / "cookies.txt"
    if cookie_file.is_file():
        opts["cookiefile"] = str(cookie_file)
    return opts

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
    if 'rumble' in u: return 'Rumble'
    if 'odysee' in u or 'lbry' in u: return 'Odysee'
    if 'bitchute' in u: return 'BitChute'
    if 'bilibili' in u: return 'Bilibili'
    if 'threads' in u: return 'Threads'
    if 'linkedin' in u: return 'LinkedIn'
    if 'vk.com' in u or 'vk.ru' in u: return 'VK'
    if 'xvideos' in u: return 'Xvideos'
    if 'pinterest' in u: return 'Pinterest'
    if 'diskwala' in u: return 'DiskWala'
    # Any other site yt-dlp can reach is treated as a generic external platform.
    return 'Other'

def fetch_info(url, task_id=None, cookiefile=None):
    """Fetches media info from URL with caching.

    cookiefile: optional path to a Netscape cookie file supplied per-request
    (e.g. from the frontend Cookies field), overriding env/cookies.txt.
    """
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

    _apply_cookies(opts, cookiefile=cookiefile)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        msg = str(e)
        if "confirm you" in msg or "Sign in" in msg or "bot" in msg.lower():
            raise Exception(
                "YouTube blocked this request (bot check). Supply YouTube "
                "cookies via the Cookies field (Advanced) or the YTDLP_COOKIES "
                "env var, then retry."
            )
        raise

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

def download_media(url, mode='video', format_id='best', task_id=None,
                   subtitles=None, playlist=False, god_mode=False, preset=None,
                   cookiefile=None):
    """Downloads media from URL. Fast mode: tries direct URL first.

    subtitles: list of language codes (e.g. ['en','es']) to embed/download.
    playlist: if True, allow yt-dlp to download the whole playlist.
    god_mode: max-speed path — aggressive aria2c concurrency, HTTP/2,
        parallel fragment downloads and fastest ffmpeg encode.
    preset: 'best' | '4k' | 'hdr' | 'audio' — overrides format selection.
    """
    # Audio mode always downloads server-side and extracts a real, playable MP3.
    # YouTube's audio-only DASH streams (m4a/opus direct URLs) are often
    # unplayable in browsers and expire quickly, so fast mode is skipped.
    if mode != "audio" and not subtitles and not playlist:
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

    concurrent = 32 if god_mode else 16
    opts = {
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "socket_timeout": 30,
        "retries": 10 if god_mode else 3,
        "fragment_retries": 10 if god_mode else 3,
        "concurrent_fragment_downloads": concurrent,
        "http_headers": {"Connection": "keep-alive"},
    }

    if not playlist:
        opts["no_playlist"] = True

    if subtitles:
        opts["writesubtitles"] = True
        opts["writeautomaticsub"] = True
        opts["subtitleslangs"] = list(subtitles) + ["en"]
        opts["subtitlesformat"] = "srt"
        opts["postprocessors"] = opts.get("postprocessors", []) + [{
            "key": "FFmpegEmbedSubtitle"
        }]

    aria2c = shutil.which("aria2c")
    if aria2c:
        # God mode maxes out aria2c split/connections for elite throughput.
        if god_mode:
            opts["external_downloader"] = "aria2c"
            opts["external_downloader_args"] = [
                "-x", "16", "-s", "64", "-k", "4M",
                "--min-split-size=1M", "--max-tries=10",
                "--max-connection-per-server=16", "--continue=true",
                "--optimize-concurrent-downloads", "--http2",
            ]
        else:
            opts["external_downloader"] = "aria2c"
            opts["external_downloader_args"] = ["-x", "16", "-s", "16", "-k", "1M"]

    if mode == "audio":
        if FFMPEG_OK:
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320" if god_mode else "192"
            }]
        else:
            opts["format"] = "bestaudio/best"
    else:
        if not FFMPEG_OK:
            opts["format"] = "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best"
        elif format_id and format_id != "best":
            opts["format"] = f"{format_id}+bestaudio/best"
            opts["merge_output_format"] = "mp4"
        elif preset == "4k":
            opts["format"] = "bestvideo[height<=2160]+bestaudio/best"
            opts["merge_output_format"] = "mkv"
        elif preset == "hdr":
            opts["format"] = "bestvideo[height<=2160][dynamic_range=hdr]+bestaudio/best"
            opts["merge_output_format"] = "mkv"
        elif preset == "audio":
            opts["format"] = "bestaudio/best"
            opts["merge_output_format"] = "mp3"
        else:
            opts["format"] = "bestvideo+bestaudio/best"
            opts["merge_output_format"] = "mp4"

    _apply_cookies(opts, cookiefile=cookiefile)

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

    size = p.stat().st_size
    if size > 4 * 1024 * 1024 * 1024:
        # Keep server storage sane — refuse oversized files.
        try:
            p.unlink()
        except Exception:
            pass
        raise Exception("File is larger than 4 GB and cannot be downloaded here. Try a lower quality or a direct download link.")

    return {
        "title": info.get("title", "media"),
        "filename": p.name,
        "ext": p.suffix[1:],
        "filesize": size,
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


def download_batch(urls, mode='video', format_id='best', subtitles=None,
                   playlist=False, on_item=None, god_mode=False, preset=None):
    """Downloads multiple URLs, returning a list of per-item results.

    on_item(task_id, index, result_or_error) is called as each finishes.
    Each URL is downloaded in its own worker so progress is tracked per item.
    """
    from neo.core.tasks import create_task, get_task_status

    results = [None] * len(urls)

    def worker(idx, url):
        try:
            res = download_media(url, mode=mode, format_id=format_id,
                                 subtitles=subtitles, playlist=playlist,
                                 god_mode=god_mode, preset=preset,
                                 task_id=None)
            results[idx] = {"url": url, "success": True, "result": res}
        except Exception as e:
            results[idx] = {"url": url, "success": False, "error": str(e)}
        if on_item:
            on_item(idx, results[idx])

    tasks_ids = []
    for idx, url in enumerate(urls):
        tid = create_task(worker, idx, url)
        tasks_ids.append(tid)

    # Wait for all to finish.
    for tid in tasks_ids:
        while True:
            st = get_task_status(tid)
            if st and st['status'] in ('completed', 'failed'):
                break
            time.sleep(0.2)

    return results
