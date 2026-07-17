from flask import Blueprint, request, jsonify, url_for, send_file, render_template, session, redirect, Response, stream_with_context
from pathlib import Path
import os
import tempfile
import time
import urllib.parse

from neo.core.engine import (
    fetch_info, download_media, search_media, get_site_label,
    validate_cookie_text, download_batch, get_youtube_stream,
    DOWNLOADS as ENGINE_DOWNLOADS,
)
from neo.core.processor import clip_media, remove_watermark, erase_metadata
from neo.core.auth_tokens import user_for_token
from neo.core.tasks import create_task, get_task_status
from neo.db_adapter import record_link

# Sites restricted to authenticated users only.
_GATED_HOSTS = ("diskwala.com", "www.diskwala.com")


def _current_user():
    """Resolve the active user from session or X-API-Key header."""
    if session.get('user_id'):
        return session['user_id']
    token = request.headers.get('X-API-Key') or request.args.get('api_key')
    return user_for_token(token) if token else None


def _is_gated(url):
    u = (url or "").lower()
    return any(h in u for h in _GATED_HOSTS)


def _require_login_for(url):
    """Redirect anonymous users to /login when the URL is login-gated."""
    if _is_gated(url) and not _current_user():
        return redirect("/login")
    return None


def _cookie_file_from_request(data):
    """Write per-request Netscape cookies (if any) to a temp file.

    Returns the temp path or None. Raises a 400 with a clear message when the
    supplied cookie text is malformed so the user is not left with a cryptic
    yt-dlp parse error after the server timeout.
    """
    cookies = (data.get("cookies") or "").strip()
    if not cookies:
        return None
    ok, reason = validate_cookie_text(cookies)
    if not ok:
        from flask import jsonify
        # Signal the caller to surface a clean client error instead of writing.
        raise ValueError(f"Cookie format invalid: {reason}")
    try:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, prefix="neo_req_cookies_"
        )
        tmp.write(cookies)
        tmp.close()
        return tmp.name
    except OSError:
        return None


from neo.core.logger import logger

api_bp = Blueprint('api', __name__)

# Use the engine's resolved downloads dir so serve/preview read from the same
# location yt-dlp actually wrote to (which falls back to /tmp on Vercel).
DOWNLOADS = ENGINE_DOWNLOADS

PLAYABLE = {'.mp4', '.webm', '.mkv', '.mov', '.avi', '.ts', '.3gp', '.ogg',
            '.mp3', '.wav', '.m4a', '.aac', '.flac', '.opus', '.wma'}
VIDEO_EXTS = {'mp4', 'webm', 'mkv', 'mov', 'avi', 'ts', '3gp', 'ogg'}
AUDIO_EXTS = {'mp3', 'wav', 'm4a', 'aac', 'flac', 'opus', 'wma'}

MIME = {
    'mp4': 'video/mp4', 'webm': 'video/webm', 'mkv': 'video/x-matroska',
    'mov': 'video/quicktime', 'avi': 'video/x-msvideo', 'ts': 'video/mp2t',
    '3gp': 'video/3gpp', 'ogg': 'video/ogg', 'mp3': 'audio/mpeg',
    'wav': 'audio/wav', 'm4a': 'audio/mp4', 'aac': 'audio/aac',
    'flac': 'audio/flac', 'opus': 'audio/ogg', 'wma': 'audio/x-ms-wma',
}


def safe_filename(name):
    name = Path(name).name
    if '..' in name or '/' in name or '\\' in name:
        return None
    if len(name) > 255:
        return None
    return name


def _download_url(filename):
    return url_for('api.serve_file', filename=filename)


@api_bp.route("/cookies/status", methods=["GET"])
def cookies_status():
    """Report whether server-side YouTube cookies are configured.

    Lets the frontend show a clear 'cookies active / add cookies' indicator
    and refuse YouTube downloads up-front instead of hitting the bot-check.
    """
    env_cookies = os.environ.get("YTDLP_COOKIES", "").strip()
    cookie_file = Path(__file__).parent.parent.parent.parent / "cookies.txt"
    active = bool(env_cookies) or cookie_file.is_file()
    return jsonify({
        "success": True,
        "env_configured": bool(env_cookies),
        "cookiefile_present": cookie_file.is_file(),
        "active": active,
        "message": (
            "YouTube cookies are active." if active
            else "No YouTube cookies configured. YouTube will block downloads "
                 "with a bot-check. Add YTDLP_COOKIES env var or paste cookies "
                 "in the Advanced panel."
        ),
    })


@api_bp.route("/youtube/stream", methods=["POST"])
def youtube_stream():
    """Resolve a YouTube stream WITHOUT contacting YouTube from our server.

    Uses a public Piped instance so Vercel's datacenter IP never trips
    YouTube's bot-check. Returns a direct CDN url the browser fetches via
    the same-origin /save proxy. Mode: 'video' (default) or 'audio'.
    """
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    mode = data.get("mode", "video")
    if not url or "youtube" not in url.lower():
        return jsonify({"success": False, "error": "Not a YouTube URL"}), 400
    try:
        stream_url, title, ext = get_youtube_stream(url, mode=mode)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400
    if not stream_url:
        return jsonify({
            "success": False,
            "error": "Could not resolve a YouTube stream via fallback. "
                     "Try setting YTDLP_COOKIES or deploy on Hugging Face Spaces.",
        }), 502
    return jsonify({
        "success": True,
        "title": title,
        "ext": ext,
        "stream_url": stream_url,
        "save_url": "/save?url=" + urllib.parse.quote(stream_url, safe="") +
                   "&name=" + urllib.parse.quote((title or "youtube") + "." + ext),
    })


@api_bp.route("/info", methods=["POST"])
def get_info():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"success": False, "error": "URL required"}), 400

    gate = _require_login_for(url)
    if gate:
        return gate

    try:
        cookie_file = _cookie_file_from_request(data)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    try:
        info = fetch_info(url, cookiefile=cookie_file)
        record_link(url, action="view", mode=data.get("mode", "video"),
                    title=info.get("title", ""), ip=request.remote_addr,
                    session_id=session.get("session_id", ""))
        return jsonify({"success": True, "data": info})
    except Exception as e:
        record_link(url, action="view", mode=data.get("mode", "video"),
                    status="error", ip=request.remote_addr,
                    session_id=session.get("session_id", ""))
        return jsonify({"success": False, "error": str(e)}), 400


@api_bp.route("/download", methods=["POST"])
def download():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    mode = data.get("mode", "video")
    format_id = data.get("format", "best")
    subtitles = data.get("subtitles") or None
    playlist = bool(data.get("playlist", False))
    god_mode = bool(data.get("god_mode", False))
    preset = data.get("preset") or None

    if not url:
        return jsonify({"success": False, "error": "URL required"}), 400

    gate = _require_login_for(url)
    if gate:
        return gate

    try:
        cookie_file = _cookie_file_from_request(data)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    def _run():
        return download_media(url, mode=mode, format_id=format_id,
                              subtitles=subtitles, playlist=playlist,
                              god_mode=god_mode, preset=preset,
                              cookiefile=cookie_file)

    task_id = create_task(_run)
    while True:
        st = get_task_status(task_id)
        if st and st['status'] in ('completed', 'failed'):
            break
        time.sleep(0.2)

    if st['status'] == 'failed':
        logger.error(f"Download failed for {url}: {st.get('error')}")
        record_link(url, action="download", mode=mode, status="error",
                    ip=request.remote_addr, session_id=session.get("session_id", ""))
        return jsonify({"success": False, "error": st.get('error') or "Download failed"}), 400

    result = st['result']
    if result.get("direct_url"):
        # Fast mode — stream directly from the CDN.
        record_link(url, action="download", mode=mode, status="success",
                    title=result.get("title"), ip=request.remote_addr,
                    session_id=session.get("session_id", ""))
        return jsonify({
            "success": True,
            "title": result.get("title"),
            "ext": result.get("ext"),
            "site": result.get("site"),
            "direct_url": result["direct_url"],
        })

    filename = result.get("filename")
    if not filename:
        record_link(url, action="download", mode=mode, status="error",
                    ip=request.remote_addr, session_id=session.get("session_id", ""))
        return jsonify({"success": False, "error": "Download produced no file"}), 500

    record_link(url, action="download", mode=mode, status="success",
                title=result.get("title"), ip=request.remote_addr,
                session_id=session.get("session_id", ""))
    return jsonify({
        "success": True,
        "title": result.get("title"),
        "ext": result.get("ext"),
        "site": result.get("site"),
        "filename": filename,
        "download_url": _download_url(filename),
        "player_url": url_for('api.play', filename=filename),
        "filesize": result.get("filesize"),
    })


@api_bp.route("/batch", methods=["POST"])
def batch_download():
    data = request.get_json(silent=True) or {}
    raw = data.get("urls")
    # Accept either a JSON list or a newline/comma-separated string.
    if isinstance(raw, list):
        urls = [str(u).strip() for u in raw if str(u).strip()]
    else:
        urls = [u.strip() for u in str(raw or "").replace("\r", "\n").split("\n") if u.strip()]
        if not urls:
            urls = [u.strip() for u in str(raw or "").split(",") if u.strip()]

    if not urls:
        return jsonify({"success": False, "error": "No URLs provided"}), 400

    mode = data.get("mode", "video")
    format_id = data.get("format", "best")
    subtitles = data.get("subtitles") or None
    playlist = bool(data.get("playlist", False))
    god_mode = bool(data.get("god_mode", False))
    preset = data.get("preset") or None

    # Gate: if ANY url is login-gated, require login.
    for u in urls:
        gate = _require_login_for(u)
        if gate:
            return gate

    try:
        results = download_batch(urls, mode=mode, format_id=format_id,
                                 subtitles=subtitles, playlist=playlist,
                                 god_mode=god_mode, preset=preset)
    except Exception as e:
        logger.error(f"Batch download failed: {e}", exc_info=True)
        for u in urls:
            record_link(u, action="download", mode=mode, status="error",
                        ip=request.remote_addr, session_id=session.get("session_id", ""))
        return jsonify({"success": False, "error": str(e)}), 400

    for res in results:
        u = res.get("url", "")
        record_link(u, action="download", mode=mode,
                    status="success" if res.get("success") else "error",
                    ip=request.remote_addr, session_id=session.get("session_id", ""))

    return jsonify({"success": True, "count": len(results), "results": results})


@api_bp.route("/search", methods=["POST"])
def search():
    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"success": False, "error": "Query required"}), 400

    try:
        results = search_media(query)
        return jsonify({"success": True, "results": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@api_bp.route("/clip", methods=["POST"])
def clip():
    data = request.get_json(silent=True) or {}
    filename = safe_filename(data.get("filename", ""))
    start = data.get("start", "00:00")
    end = data.get("end", "00:30")

    if not filename:
        return jsonify({"success": False, "error": "Filename required"}), 400

    try:
        out = clip_media(filename, start, end)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

    return jsonify({
        "success": True,
        "filename": out["filename"],
        "download_url": _download_url(out["filename"]),
    })


@api_bp.route("/remove_watermark", methods=["POST"])
def watermark():
    data = request.get_json(silent=True) or {}
    filename = safe_filename(data.get("filename", ""))
    auto = data.get("auto", False)
    scrub = data.get("scrub", True)

    if not filename:
        return jsonify({"success": False, "error": "Filename required"}), 400

    try:
        out = remove_watermark(filename, auto=auto, scrub=scrub)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

    return jsonify({
        "success": True,
        "filename": out["filename"],
        "download_url": _download_url(out["filename"]),
    })


@api_bp.route("/wipe", methods=["POST"])
def wipe():
    data = request.get_json(silent=True) or {}
    filename = safe_filename(data.get("filename", ""))

    if not filename:
        return jsonify({"success": False, "error": "Filename required"}), 400

    try:
        out = erase_metadata(filename)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

    return jsonify({
        "success": True,
        "filename": out["filename"],
        "download_url": _download_url(out["filename"]),
    })


@api_bp.route("/save")
def save_url():
    """Proxy a direct CDN URL to the browser as a forced download.

    Browsers ignore the `download` attribute on cross-origin links, so a raw
    direct_url opens a new tab instead of saving. Streaming it through our
    origin with Content-Disposition: attachment guarantees a real download.
    """
    import urllib.request
    url = (request.args.get("url") or "").strip()
    name = (request.args.get("name") or "neo-media").strip() or "neo-media"
    if not url or not url.startswith("http"):
        return jsonify({"success": False, "error": "Invalid URL"}), 400

    # Disallow obvious local/metadata addresses to avoid SSRF to internal hosts.
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ""
    if host in ("localhost", "127.0.0.1", "0.0.0.0", "169.254.169.254"):
        return jsonify({"success": False, "error": "Blocked host"}), 403

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        remote = urllib.request.urlopen(req, timeout=60)

        def gen():
            while True:
                chunk = remote.read(1024 * 256)
                if not chunk:
                    break
                yield chunk
            remote.close()

        ext = Path(url.split("?")[0]).suffix or ""
        safe_name = f"{Path(name).stem}{ext}"
        headers = {
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "Cache-Control": "no-store",
        }
        ct = remote.headers.get("Content-Type")
        if ct:
            headers["Content-Type"] = ct
        cl = remote.headers.get("Content-Length")
        if cl:
            headers["Content-Length"] = cl
        return Response(stream_with_context(gen()), headers=headers)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@api_bp.route("/serve/<filename>")
def serve_file(filename):
    filename = safe_filename(filename)
    if not filename:
        return jsonify({"success": False, "error": "Invalid filename"}), 400
    if ".." in filename or filename.startswith("/") or filename.startswith("\\"):
        return jsonify({"success": False, "error": "Access denied"}), 403
    filepath = DOWNLOADS / filename
    if filepath.resolve().parent != DOWNLOADS.resolve():
        return jsonify({"success": False, "error": "Access denied"}), 403
    if not filepath.is_file():
        return jsonify({"success": False, "error": "File not found"}), 404
    return send_file(str(filepath), as_attachment=True, download_name=filename)


@api_bp.route("/preview/<filename>")
def preview_file(filename):
    filename = safe_filename(filename)
    if not filename:
        return jsonify({"success": False, "error": "Invalid filename"}), 400
    filepath = DOWNLOADS / filename
    if filepath.resolve().parent != DOWNLOADS.resolve():
        return jsonify({"success": False, "error": "Access denied"}), 403
    if not filepath.is_file():
        return jsonify({"success": False, "error": "Not found"}), 404
    ext = Path(filename).suffix.lower().lstrip('.')
    return send_file(str(filepath), mimetype=MIME.get(ext, 'application/octet-stream'))


@api_bp.route("/play/<filename>")
def play(filename):
    filename = safe_filename(filename)
    if not filename:
        return jsonify({"success": False, "error": "Invalid filename"}), 400
    filepath = DOWNLOADS / filename
    if filepath.resolve().parent != DOWNLOADS.resolve():
        return jsonify({"success": False, "error": "Access denied"}), 403
    if not filepath.is_file():
        return jsonify({"success": False, "error": "Not found"}), 404
    ext = Path(filename).suffix.lower()
    if ext not in PLAYABLE:
        return jsonify({"success": False, "error": "Unsupported format"}), 400
    is_video = ext.lstrip('.') in VIDEO_EXTS
    files = sorted(
        [f.name for f in DOWNLOADS.iterdir() if f.suffix.lower() in ('.mp4', '.webm', '.mov', '.mp3', '.wav', '.m4a')],
        key=lambda x: os.path.getmtime(DOWNLOADS / x), reverse=True
    )
    return render_template("player.html", filename=filename, title=Path(filename).stem.replace('_', ' '), is_video=is_video, files=files, ext=ext.lstrip('.'))
