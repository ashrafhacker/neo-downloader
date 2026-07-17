from flask import Blueprint, request, jsonify, url_for, send_file, render_template, session, redirect
from pathlib import Path
import os

from neo.core.engine import fetch_info, download_media, search_media, get_site_label
from neo.core.processor import clip_media, remove_watermark

# Sites restricted to authenticated users only.
_GATED_HOSTS = ("diskwala.com", "www.diskwala.com")


def _is_gated(url):
    u = (url or "").lower()
    return any(h in u for h in _GATED_HOSTS)


def _require_login_for(url):
    """Redirect anonymous users to /login when the URL is login-gated."""
    if _is_gated(url) and not session.get("user_id"):
        return redirect("/login")
    return None


from neo.core.logger import logger

api_bp = Blueprint('api', __name__)

BASE_DIR = Path(__file__).parent.parent.parent.parent
DOWNLOADS = BASE_DIR / "downloads"
DOWNLOADS.mkdir(exist_ok=True)

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
        info = fetch_info(url)
        return jsonify({"success": True, "data": info})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@api_bp.route("/download", methods=["POST"])
def download():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    mode = data.get("mode", "video")
    format_id = data.get("format", "best")

    if not url:
        return jsonify({"success": False, "error": "URL required"}), 400

    gate = _require_login_for(url)
    if gate:
        return gate

    try:
        result = download_media(url, mode=mode, format_id=format_id)
    except Exception as e:
        logger.error(f"Download failed for {url}: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400

    if result.get("direct_url"):
        # Fast mode — stream directly from the CDN.
        return jsonify({
            "success": True,
            "title": result.get("title"),
            "ext": result.get("ext"),
            "site": result.get("site"),
            "direct_url": result["direct_url"],
        })

    filename = result.get("filename")
    if not filename:
        return jsonify({"success": False, "error": "Download produced no file"}), 500

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
