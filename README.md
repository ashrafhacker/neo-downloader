<p align="center">
  <img src="https://img.shields.io/badge/status-active-success" alt="Status">
  <img src="https://img.shields.io/badge/platform-cross--platform-blueviolet" alt="Platform">
  <img src="https://img.shields.io/badge/sites-1000%2B-orange" alt="Sites">
  <img src="https://img.shields.io/badge/god%20mode-v2.5-8b5cf6" alt="God Mode">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="License">
  <img src="https://img.shields.io/badge/python-3.12%2B-3776AB" alt="Python">
</p>

<div align="center">
  <img src="https://img.shields.io/badge/made%20with-Python-3776AB" alt="Python">
  <img src="https://img.shields.io/badge/powered%20by-yt--dlp-FF0000" alt="yt-dlp">
  <img src="https://img.shields.io/badge/uses-ffmpeg-007ACC" alt="ffmpeg">
  <img src="https://img.shields.io/badge/UI-glassmorphism-8b5cf6" alt="Glassmorphism">
</div>

<br>

<div align="center">
  <h1>⚡ neo</h1>
  <p><strong>Paste any link. Watch instantly. Download clean.</strong></p>
  <p>A premium, self-hosted media powerhouse — stream, download, clip, and convert media from <strong>1000+ platforms</strong> through a sleek glassmorphism UI, with an optional <strong>God Mode</strong> for elite-speed pulls, a built-in <strong>watermark remover</strong>, and full <strong>metadata/EXIF erasure</strong>.</p>
</div>

<br>

<div align="center">
  <picture>
    <img alt="neo hero" src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=12,14,24&height=120&section=header&text=neo%20%E2%80%A2%20download%20%E2%80%A2%20play%20%E2%80%A2%20clean&fontSize=28&fontAlignY=38&desc=1000%2B%20sites%20%E2%80%A2%20god%20mode%20%E2%80%A2%20watermark%20remover%20%E2%80%A2%20metadata%20wipe&descAlignY=58">
  </picture>
</div>

> ⚠️ **Educational Purpose Only.** This tool is provided for learning and educational use. You are solely responsible for how you use it. Respect the terms of service and copyright of each platform, and only download content you have the right to access. **The authors are not responsible for any misuse or any consequences arising from its use.**

<br>

<p align="center">
  <a href="#-features">Features</a> •
  <a href="#-god-mode">God Mode</a> •
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-deploy-for-free">Free Deploy</a> •
  <a href="#-api-reference">API</a> •
  <a href="#-tech-stack">Tech Stack</a> •
  <a href="#-security">Security</a> •
  <a href="#-changelog">Changelog</a>
</p>

---

<h2 id="-features">✨ Features</h2>

<table align="center">
  <tr>
    <td align="center" width="25%"><img src="https://img.icons8.com/fluency/48/video-playlist.png" width="38"/><br><b>Universal Player</b><br><sub>Watch any link instantly, no external player. Glass UI with full controls + PiP.</sub></td>
    <td align="center" width="25%"><img src="https://img.icons8.com/fluency/48/link.png" width="38"/><br><b>Auto URL Detection</b><br><sub>Paste a URL and see title, thumbnail, duration & platform before downloading.</sub></td>
    <td align="center" width="25%"><img src="https://img.icons8.com/fluency/48/audio-wave.png" width="38"/><br><b>Audio Extraction</b><br><sub>One-click <b>real MP3</b> extraction via ffmpeg — playable in any browser.</sub></td>
    <td align="center" width="25%"><img src="https://img.icons8.com/fluency/48/cut.png" width="38"/><br><b>Clip Maker</b><br><sub>Trim to your favorite moments with precise start/end timestamps.</sub></td>
  </tr>
  <tr>
    <td align="center" width="25%"><img src="https://img.icons8.com/fluency/48/watermark.png" width="38"/><br><b>Watermark Cleaner</b><br><sub>Multi-zone delogo + metadata scrub (EXIF/GPS/author).</sub></td>
    <td align="center" width="25%"><img src="https://img.icons8.com/fluency/48/rocket.png" width="38"/><br><b>God Mode</b><br><sub>Elite-speed pulls: 64-way aria2c splits, HTTP/2, 4K/HDR presets.</sub></td>
    <td align="center" width="25%"><img src="https://img.icons8.com/fluency/48/clipboard.png" width="38"/><br><b>One-Click Paste</b><br><sub>Clipboard paste + local history of last 20 links.</sub></td>
    <td align="center" width="25%"><img src="https://img.icons8.com/fluency/48/monitor.png" width="38"/><br><b>Admin Dashboard</b><br><sub>Live stats, capture gallery & session drilldown at <code>/admin</code>.</sub></td>
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

<h2 id="-god-mode">🚀 God Mode & Advanced Engine</h2>

<p align="center"><i>Toggle <b>God Mode</b> in the Advanced panel for maximum throughput.</i></p>

<div align="center">

| Capability | Standard | God Mode |
|:---|:---:|:---:|
| Concurrent fragment downloads | default | **32** |
| aria2c connection splits | — | **64** |
| HTTP/2 multiplexing | off | **on** |
| Resolution presets | best | **4K / HDR / audio-only** |
| Large-file guard | 2 GB | **4 GB** |

</div>

**Presets** let you pick the job in one click:

- 🎬 **4K** — maximum-resolution video pulls
- 🌈 **HDR** — high-dynamic-range streams when available
- 🎵 **Audio** — direct audio-only extraction (MP3/FLAC)

**Privacy toolkit** (always available):

- 🧹 **Watermark Remover** — multi-zone `ffmpeg delogo` with auto-detect and manual XY presets
- 🔒 **Wipe ALL Metadata** — strips `-map_metadata -1`, chapters, and EXIF/GPS/author tags via `-fflags +bitexact`

---

<h2 id="supported-platforms">🌐 Supported Platforms</h2>

> YouTube, YouTube Shorts, Instagram (Reels & Posts), TikTok, Twitter/X, Facebook, Telegram, **Terabox**, Reddit, Twitch, Spotify, SoundCloud, Vimeo, Dailymotion, Vine, VK, Pinterest, Tumblr, LinkedIn, Threads, Bluesky, Flickr, 9GAG, IMDb, Steam, Rumble, Odysee, BitChute, Bilibili, and **1000+ more** via [yt-dlp](https://github.com/yt-dlp/yt-dlp).

> Any other public site yt-dlp can reach is handled automatically as a generic external platform — just paste the link.

> **Note:** DiskWala (`diskwala.com`) is available **to logged-in users only**. Anonymous visitors are redirected to the login page when they try to fetch or download from it.

### Format Support

| Type | Formats |
|------|---------|
| **Video** | MP4, WebM, MKV, MOV, AVI, TS, 3GP, OGG |
| **Audio** | MP3, WAV, M4A, AAC, FLAC, Opus, OGG |
| **Image** | JPEG, PNG, GIF, BMP, WebP (watermark clean only) |

---

<h2 id="-quick-start">⚡ Quick Start</h2>

```bash
# Clone
git clone https://github.com/ashrafhacker/neo-downloader.git
cd neo-downloader

# Install dependencies
pip install -r requirements.txt

# Make sure ffmpeg is in PATH (required for clip / watermark / audio)

# Run (dev) — modular neo app (recommended)
python wsgi.py

# Or run the classic entry point (delegates to neo)
python app.py
```

Open **http://localhost:5000**

<h2 id="-deploy-for-free">🚀 Deploy for Free (No Credit Card)</h2>

**Option 1 — Vercel (easiest)**

[![Deploy to Vercel](https://vercel.com/button)](https://vercel.com/import/project?template=ashrafhacker/neo-downloader)

1. Push repo to GitHub, then import into [vercel.com](https://vercel.com)
2. Set env vars in Vercel dashboard:
   - `ADMIN_PASSWORD` = a strong password
   - `FLASK_SECRET_KEY` = *(run `python -c "import secrets; print(secrets.token_hex(32))"`)*
3. Deploy — Vercel auto-detects `vercel.json`. App runs as a serverless function.

> **Limitations:** No persistent file storage (downloads lost after cold starts), no ffmpeg (clip/watermark disabled). Serverless 30s timeout may fail on some URLs; use direct media links for best results.

**Option 2 — Hugging Face Spaces (ffmpeg included)**

[![Hugging Face Spaces](https://img.shields.io/badge/%F0%9F%A4%94-Hugging%20Face%20Spaces-yellow)](https://huggingface.co/new-space)

1. Go to [huggingface.co/new-space](https://huggingface.co/new-space) → Name: `neo-downloader` → SDK: **Docker**
2. Connect GitHub repo `ashrafhacker/neo-downloader`
3. Add secrets: `ADMIN_PASSWORD`, `FLASK_SECRET_KEY`
4. Builds automatically. App at `https://youruser-neo-downloader.hf.space`

> ⚠️ **Docker requires HF Pro subscription** ($9/mo). Free tier only supports Gradio/Streamlit/Static apps.

**Option 3 — PythonAnywhere (simpler, no ffmpeg)**

1. Account at [pythonanywhere.com](https://pythonanywhere.com) → Web tab → Add web app → Manual config → Python 3.12
2. `pip install flask yt-dlp requests Pillow python-dotenv gunicorn`
3. Set `ADMIN_PASSWORD` in WSGI config file
4. Reload. No ffmpeg = clip & watermark disabled (download still works).

### Production Deployment (VPS)

```bash
pip install -r requirements.txt

export FLASK_SECRET_KEY="$(python -c "import secrets; print(secrets.token_hex(32))")"
export ADMIN_PASSWORD="$(python -c "import secrets; print(secrets.token_hex(16))")"

# Run with gunicorn (entry point delegates to the neo app)
gunicorn wsgi:app --bind 0.0.0.0:${PORT:-5000} --workers 2 --timeout 120
```

**Deploy to Railway / Render / Fly.io** — just connect the repo; `Procfile` and `runtime.txt` are ready.

### Environment Variables

| Variable | Description |
|----------|-------------|
| `ADMIN_PASSWORD` | **Required for production.** Password for the admin panel |
| `FLASK_SECRET_KEY` | **Required for production.** Random 64-char hex string for session signing |
| `TERABOX_COOKIE` | Cookie string for Terabox downloads |
| `MONGO_URI` | Optional — switch the DB from SQLite to MongoDB |
| `PORT` | Server port (default: 5000) |
| `FLASK_DEBUG` | Set to `1` for debug mode (default: `0`) |
| `VERCEL` | Auto-set on Vercel; routes DB + temp dirs to `/tmp` |

---

<h2 id="-security">🛡️ Security</h2>

<div align="center">

| Feature | Status |
|---------|:------:|
| Session-based authentication | ✅ |
| Rate limiting on all API endpoints | ✅ |
| Input validation & sanitization | ✅ |
| Path traversal protection | ✅ |
| SQL injection prevention (parameterized queries) | ✅ |
| CSRF token generation | ✅ |
| Security headers (CSP, X-Frame-Options, etc.) | ✅ |
| SSRF guard on `/save` proxy (blocks localhost / 169.254.169.254) | ✅ |
| CORS restricted to same origin | ✅ |
| `.env` support via python-dotenv | ✅ |

</div>

---

<h2 id="-api-reference">📡 API Reference</h2>

### User Routes
| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | Main download page |
| `/play/<filename>` | GET | Dedicated player page with library sidebar |
| `/download` | POST | Download media from URL (video or audio MP3); forwards `god_mode` & `preset` |
| `/info` | POST | Fetch media metadata (title, thumbnail, duration, platform) |
| `/preview/<filename>` | GET | Stream media for inline browser playback |
| `/serve/<filename>` | GET | Direct file download (auto-cleanup after 5 min) |
| `/save` | GET | Same-origin proxy that forces `Content-Disposition: attachment` (fixes cross-origin "opens new tab" issue) |
| `/clip` | POST | Clip video by start/end timestamp |
| `/remove_watermark` | POST | Remove watermark & scrub metadata |
| `/wipe` | POST | Erase all metadata/EXIF from a file |

### Admin Routes
| Route | Method | Description |
|-------|--------|-------------|
| `/admin` | GET | Admin dashboard |
| `/admin/stats` | GET | Aggregated statistics JSON |
| `/admin/users` | GET | Per-user session summaries |
| `/admin/locations` | GET | Geolocation coordinates |
| `/admin/logs` | GET | Raw download log (last 500) |
| `/admin/all` | GET | All downloads + captures |
| `/admin/delete-all` | POST | Bulk delete |
| `/admin/captures/delete/<id>` | POST | Delete single capture |

---

<h2 id="-tech-stack">🛠 Tech Stack</h2>

<div align="center">

| Layer | Tools |
|-------|-------|
| **Backend** | Python 3.12, Flask, yt-dlp, ffmpeg, Pillow, Gunicorn |
| **Database** | SQLite (auto-created `logs.db`) · MongoDB (optional via `MONGO_URI`) |
| **Frontend** | HTML5, CSS3 (glassmorphism), Vanilla JavaScript, Inter font |
| **Download engine** | aria2c concurrency, 64-split + HTTP/2, 4K/HDR/audio presets |
| **Infrastructure** | Cross-platform (Win/Linux/macOS), Vercel / HF Spaces / Railway / Render / Fly |

</div>

---

<h2 id="-changelog">📋 Changelog</h2>

### v2.5 (Latest)
- 🚀 **God Mode** — elite-speed download path: 32 concurrent fragments, 64-way aria2c splits, HTTP/2, 4 GB guard
- 🎛️ **Presets** — one-click 4K / HDR / audio-only quality selection
- 🧹 **Built-in watermark remover** — multi-zone `ffmpeg delogo` with auto-detect + manual XY presets
- 🔒 **Metadata/EXIF erasure** — new `/wipe` route strips all tags via `-map_metadata -1 -fflags +bitexact`
- 🎵 **MP3 / MP4 download buttons** — direct, attachment-forced downloads on the result card
- 📥 **Cross-origin download fix** — new same-origin `/save` proxy forces `Content-Disposition: attachment`; frontend blob fallback
- 🛡️ **Vercel runtime 500 fix** — all import-time filesystem writes fall back to `/tmp` on read-only FS

### v2.4
- 🧩 Refactored into a modular `neo/` app (core engine, processor, tasks, db adapter, blueprints)
- 🎵 **Audio mode fixed** — now downloads server-side and extracts a real, playable MP3
- 🛠️ Fixed `/serve` 404 caused by a downloads path mismatch
- 🧵 Threaded dev server to avoid empty responses on long yt-dlp calls
- ✅ Test suite updated to the top-level route contract — 29 tests passing

### v2.3
- 🌐 `wsgi.py` entry point — `gunicorn wsgi:app` for VPS, Vercel & Netlify
- 🛡️ Admin hardening — stats/users/locations/delete routes, path-traversal guards
- ⚡ Serverless Vercel optimization — `/download` rewritten for 30s timeout limit
- 🪶 Graceful module fallbacks — app starts even without yt-dlp/requests/ffmpeg

### v2.2
- 🏷️ Rebranded to **neo** — cleaner logo, streamlined naming
- 🚀 Production-ready deployment config — `Procfile`, `runtime.txt`, `requirements.txt`
- 📦 python-dotenv auto-load on startup

### v2.1
- 🎨 Complete UI redesign — clean gradient hero, feature cards, step guide, stats row
- 📸 Page screenshots captured every 15s
- 🖱️ Click tracking with element, text, position, and page
- 🗑️ Bulk delete in admin panel

### v2.0
- Premium glassmorphism UI redesign with gradient glow animations
- Auto URL info fetch on paste (title, thumbnail, duration, platform)
- URL history dropdown with localStorage (last 20)
- Picture-in-Picture for videos
- Toast notifications & multi-zone watermark auto-detect
- Dedicated player page at `/play/<filename>`

### v1.0
- Initial release with yt-dlp download engine
- Admin dashboard
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
  <img src="https://img.shields.io/badge/god%20mode-8b5cf6" alt="God Mode">
</div>
