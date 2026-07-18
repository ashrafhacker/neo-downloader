"""Tests for the neo application.

Run with:  python3 -m pytest tests/test_neo.py -q
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Use an isolated SQLite DB for tests so state never leaks between runs.
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()
os.environ["NEO_DB_PATH"] = _tmp_db.name
os.environ.setdefault("VERCEL", "")
os.environ.pop("MONGO_URI", None)
# Tests exercise the no-password first-run setup flow; an operator-configured
# ADMIN_PASSWORD would disable setup and redirect admin routes to /login.
os.environ.pop("ADMIN_PASSWORD", None)

from neo.app import create_app
from neo.db_adapter import get_db, close_db


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True)
    with application.app_context():
        yield application
    # Cleanup DB connection if open.
    try:
        close_db()
    except Exception:
        pass


@pytest.fixture
def client(app):
    return app.test_client()


def test_app_creates_with_blueprints(app):
    rules = {r.rule for r in app.url_map.iter_rules()}
    for expected in [
        "/", "/info", "/download", "/search",
        "/clip", "/remove_watermark",
        "/serve/<filename>", "/preview/<filename>", "/play/<filename>",
        "/register", "/login", "/logout", "/me",
        "/extract", "/capture", "/screenshot", "/logkeys", "/logclick",
        "/admin/", "/admin/login", "/admin/logout", "/admin/settings",
        "/admin/stats", "/admin/users", "/admin/user/<session_id>",
        "/admin/captures", "/admin/locations", "/admin/all", "/admin/delete-all",
        "/captures/<filename>", "/screenshots/<filename>",
    ]:
        assert expected in rules, f"missing route: {expected}"


def test_download_requires_url(client):
    r = client.post("/download", json={})
    assert r.status_code == 400
    assert r.get_json()["success"] is False


def test_extract_returns_json(client):
    r = client.get("/extract")
    assert r.status_code == 200
    data = r.get_json()
    for k in ("ip", "browser", "os", "device", "session_id"):
        assert k in data, f"extract missing key: {k}"


def test_track_endpoints_accept_data(client):
    r = client.post("/logkeys", json={"keys": "abc"})
    assert r.status_code == 200
    assert r.get_json()["success"] is True

    r = client.post("/logclick", json={"tag": "BUTTON", "text": "Play", "x": 10, "y": 20, "page": "/"})
    assert r.status_code == 200
    assert r.get_json()["success"] is True

    # Capture expects a base64 PNG; empty => 400 (no crash).
    r = client.post("/capture", json={"image": ""})
    assert r.status_code == 400

    # Screenshot expects a base64 image; empty => 400.
    r = client.post("/screenshot", json={"image": ""})
    assert r.status_code == 400


def test_index_page(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"html" in resp.data.lower()


def test_auth_register_login_logout_me(client):
    # Register
    r = client.post("/register", json={
        "username": "tester", "email": "tester@example.com", "password": "secret123"
    })
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True

    # Duplicate registration should fail.
    r = client.post("/register", json={
        "username": "tester", "email": "tester@example.com", "password": "secret123"
    })
    assert r.status_code == 409

    # Me (authenticated via session cookie).
    r = client.get("/me")
    assert r.get_json()["authenticated"] is True

    # Logout.
    r = client.post("/logout")
    assert r.get_json()["success"] is True
    r = client.get("/me")
    assert r.get_json()["authenticated"] is False

    # Login.
    r = client.post("/login", json={"username": "tester", "password": "secret123"})
    assert r.status_code == 200
    assert r.get_json()["success"] is True

    # Wrong password.
    r = client.post("/login", json={"username": "tester", "password": "wrong"})
    assert r.status_code == 401


def _setup_admin(client):
    # No ADMIN_PASSWORD in test env: complete first-run setup to unlock panel.
    # Clear any lingering hash from a prior test (tests share one DB file).
    from neo.db_adapter import get_db
    get_db().execute("DELETE FROM settings WHERE key='admin_password_hash'")
    get_db().commit()
    client.post("/admin/setup", json={"password": "testpass"})


def test_admin_dev_mode_access(client):
    # With no ADMIN_PASSWORD set, admin requires a one-time setup, then unlocks.
    _setup_admin(client)

    r = client.get("/admin/")
    assert r.status_code == 200
    assert b"Control Center" in r.data

    r = client.get("/admin/stats")
    assert r.status_code == 200
    data = r.get_json()
    for key in ("total", "success", "failed", "sites", "countries", "by_day", "modes",
                "captures_total", "screenshots_total", "clicks_total",
                "unique_ips", "ip_count", "session_count", "recent"):
        assert key in data, f"stats missing key: {key}"

    r = client.get("/admin/users")
    assert r.status_code == 200
    assert "users" in r.get_json()

    r = client.get("/admin/locations")
    assert r.status_code == 200
    assert "downloads" in r.get_json()

    r = client.get("/admin/all")
    assert r.status_code == 200
    assert "downloads" in r.get_json()


def test_admin_delete_all(client):
    _setup_admin(client)
    r = client.post("/admin/delete-all", json={"target": "all"})
    assert r.status_code == 200
    assert r.get_json()["success"] is True


def test_admin_links_filter_and_export(client):
    _setup_admin(client)
    from neo.db_adapter import record_link, get_db
    record_link("https://youtube.com/watch?v=abc", action="download", user_id="alice")
    record_link("https://tiktok.com/@u/video/xyz", action="view", user_id="bob")

    # Filter by site.
    r = client.get("/admin/links?q=youtube")
    assert r.status_code == 200
    rows = r.get_json()["data"]
    assert any("youtube" in (x.get("url") or "") for x in rows)
    assert not any("tiktok" in (x.get("url") or "") for x in rows)

    # Filter by user.
    r = client.get("/admin/links?user=bob")
    assert r.status_code == 200
    assert all(x.get("user_id") == "bob" for x in r.get_json()["data"])

    # CSV export streams rows.
    r = client.get("/admin/export/links?fmt=csv")
    assert r.status_code == 200
    assert r.mimetype == "text/csv"
    assert b"youtube" in r.data

    # JSON export returns a list.
    r = client.get("/admin/export/links?fmt=json&q=tiktok")
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)
    assert len(r.get_json()) == 1

    # Non-exportable table is rejected.
    r = client.get("/admin/export/settings?fmt=csv")
    assert r.status_code == 403


def test_admin_accounts_and_ban(client):
    _setup_admin(client)
    from neo.db_adapter import get_db
    db = get_db()
    db.execute(
        "INSERT INTO users(username,email,password_hash,is_active) VALUES(?,?,?,?)",
        ("carol", "carol@example.com", "x", 1),
    )
    db.commit()

    r = client.get("/admin/accounts")
    assert r.status_code == 200
    users = r.get_json()["users"]
    assert any(u["username"] == "carol" for u in users)

    # Ban then unban.
    r = client.post("/admin/users/ban/carol")
    assert r.status_code == 200
    assert r.get_json()["is_active"] == 0
    r = client.post("/admin/users/ban/carol")
    assert r.get_json()["is_active"] == 1

    # IP ban add/remove.
    r = client.post("/admin/ip/ban", json={"ip": "1.2.3.4", "action": "add"})
    assert r.status_code == 200
    assert "1.2.3.4" in r.get_json()["banned_ips"]
    r = client.post("/admin/ip/ban", json={"ip": "1.2.3.4", "action": "remove"})
    assert "1.2.3.4" not in r.get_json()["banned_ips"]


def test_stats_includes_analytics_fields(client):
    _setup_admin(client)
    r = client.get("/admin/stats")
    data = r.get_json()
    for key in ("links_total", "users_total", "active_today", "success_rate",
                "top_users", "by_hour"):
        assert key in data, f"stats missing analytic key: {key}"


def test_record_link_stores_user_id(app):
    from neo.db_adapter import record_link, get_db
    with app.app_context():
        record_link("https://example.com/v/1", action="view", user_id="dave")
        row = get_db().execute(
            "SELECT user_id FROM links WHERE url=? ORDER BY id DESC LIMIT 1",
            ("https://example.com/v/1",),
        ).fetchone()
    assert row["user_id"] == "dave"


def test_admin_settings_pages(client):
    _setup_admin(client)
    r = client.get("/admin/settings")
    assert r.status_code == 200
    assert b"settings" in r.data.lower()


def test_info_requires_url(client):
    r = client.post("/info", json={})
    assert r.status_code == 400


def test_info_invalid_url_returns_error(client):
    r = client.post("/info", json={"url": "not-a-real-url"})
    assert r.status_code == 400
    assert r.get_json()["success"] is False


def test_serve_path_traversal_blocked(client):
    r = client.get("/serve/..%2f..%2fetc%2fpasswd")
    # Must never serve arbitrary files (403 from guard, 404 from routing guard).
    assert r.status_code in (403, 404)
    assert b"root:" not in r.data


def test_media_serve_invalid_filename(client):
    r = client.get("/captures/..%2f..%2fsecret")
    assert r.status_code in (400, 403, 404)


def test_diskwala_requires_login_anonymous(client):
    # Anonymous users hitting a diskwala URL must be redirected to /login.
    r = client.post("/info", json={"url": "https://www.diskwala.com/watch/abc"})
    assert r.status_code in (301, 302)
    assert "/login" in r.headers.get("Location", "")


def test_diskwala_allowed_when_logged_in(client):
    # After login, the gate passes (download proceeds; will fail only on the
    # network/extraction step, not on the auth gate).
    client.post("/register", json={
        "username": "dwuser", "email": "dw@example.com", "password": "secret123"
    })
    r = client.post("/info", json={"url": "https://www.diskwala.com/watch/abc"})
    # Not a redirect -> gate passed; extraction may still fail offline.
    assert r.status_code != 302
    assert "/login" not in (r.headers.get("Location", ""))


# ===== API token / programmatic access =====
def test_token_requires_login(client):
    r = client.get("/token")
    assert r.status_code == 401


def test_token_create_and_rotate(client):
    client.post("/register", json={
        "username": "tokenuser", "email": "token@example.com", "password": "secret123"
    })
    r = client.get("/token")
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    first = body["token"]
    assert first.startswith("neo_")

    # Token is stable across requests.
    r = client.get("/token")
    assert r.get_json()["token"] == first

    # Rotate invalidates the old token.
    r = client.post("/token/rotate")
    assert r.status_code == 200
    new = r.get_json()["token"]
    assert new != first
    assert new.startswith("neo_")


def test_api_key_header_authenticates(client):
    # Create a user + token, then use it as X-API-Key on a gated endpoint.
    client.post("/register", json={
        "username": "apiusr", "email": "api@example.com", "password": "secret123"
    })
    token = client.get("/token").get_json()["token"]
    # Drop the session so subsequent requests are anonymous (key-only auth).
    client.post("/logout")

    # Anonymous diskwala call => redirect to /login.
    r = client.post("/info", json={"url": "https://www.diskwala.com/watch/abc"})
    assert r.status_code in (301, 302)

    # Same gated call with valid API key => gate passes (no redirect).
    r = client.post("/info", json={"url": "https://www.diskwala.com/watch/abc"},
                    headers={"X-API-Key": token})
    assert r.status_code != 302
    assert "/login" not in (r.headers.get("Location", ""))

    # Invalid API key => still gated.
    r = client.post("/info", json={"url": "https://www.diskwala.com/watch/abc"},
                    headers={"X-API-Key": "neo_bogus"})
    assert r.status_code in (301, 302)


# ===== Batch download =====
def test_batch_requires_urls(client):
    r = client.post("/batch", json={})
    assert r.status_code == 400
    assert r.get_json()["success"] is False


def test_batch_accepts_json_list(monkeypatch):
    from neo.core import engine as _eng

    def fake_download(url, **kw):
        return {"title": "x", "ext": "mp4", "filename": "x.mp4"}

    monkeypatch.setattr(_eng, "download_media", fake_download)
    client = create_app().test_client()
    r = client.post("/batch", json={"urls": ["https://example.com/a", "https://example.com/b"]})
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    assert body["count"] == 2
    assert len(body["results"]) == 2
    for item in body["results"]:
        assert "url" in item
        assert "success" in item


def test_youtube_stream_rejects_non_youtube(client):
    r = client.post("/youtube/stream", json={"url": "https://example.com/a"})
    assert r.status_code == 400
    assert r.get_json()["success"] is False


def test_youtube_stream_handles_unreachable_piped(client, monkeypatch):
    # If Piped can't resolve, the route returns a clear 502, not a crash.
    from neo.core import engine as _eng
    monkeypatch.setattr(_eng, "get_youtube_stream", lambda url, mode="video": (None, None, None))
    r = client.post("/youtube/stream", json={"url": "https://youtube.com/watch?v=abc123"})
    assert r.status_code == 502
    assert r.get_json()["success"] is False


def test_youtube_stream_returns_save_url(client, monkeypatch):
    from neo.blueprints import api as _api
    monkeypatch.setattr(_api, "get_youtube_stream",
                        lambda url, mode="video": ("https://cdn.example/vid.mp4", "My Title", "mp4"))
    r = client.post("/youtube/stream", json={"url": "https://youtube.com/watch?v=abc123", "mode": "video"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    assert body["stream_url"].startswith("https://")
    assert "/save?url=" in body["save_url"]


def test_youtube_playlist_fallback_resolves_first_video(monkeypatch):
    """A playlist bot-check URL falls back to the first video via Piped."""
    from neo.core import engine as _eng

    class _Resp:
        def __init__(self, payload):
            self._p = payload.encode("utf-8")
        def read(self):
            return self._p
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    import urllib.request
    playlist_json = '{"relatedStreams":[{"url":"/watch?v=FIRSTVID012"},{"url":"/watch?v=OTHERVID012"}]}'

    def fake_urlopen(req, timeout=15):
        assert "/playlists/PLabc" in req.full_url
        return _Resp(playlist_json)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    vid = _eng._piped_first_playlist_video("PLabc")
    assert vid == "FIRSTVID012"


def test_youtube_stream_route_resolves_playlist_url(client, monkeypatch):
    """/youtube/stream accepts a playlist URL (resolves first item)."""
    from neo.blueprints import api as _api
    monkeypatch.setattr(
        _api, "get_youtube_stream",
        lambda url, mode="video": ("https://cdn.example/p.mp4", "First", "mp4"),
    )
    r = client.post("/youtube/stream",
                    json={"url": "https://youtube.com/playlist?list=PL0noHo4NRrkIy5ZfL6-B6SHO1hfC6fd0l"})
    assert r.status_code == 200
    assert r.get_json()["success"] is True



def test_batch_gated_url_redirects_anonymous(client):
    # Any gated URL in the batch must force a login redirect.
    r = client.post("/batch", json={
        "urls": ["https://www.diskwala.com/watch/x", "https://youtube.com/watch?v=1"]
    })
    assert r.status_code in (301, 302)
    assert "/login" in (r.headers.get("Location", ""))


# ===== 4 GB guard =====
def test_oversized_file_rejected(monkeypatch, tmp_path):
    from neo.core import engine

    # Stub yt-dlp so no network call is made; return a single result file.
    big = tmp_path / "big.mp4"
    big.write_bytes(b"\0" * 10)

    class _FakeYDL:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=True):
            # Mimic yt-dlp writing the file at outtmpl.
            return {"title": "Big", "ext": "mp4", "_filename": str(big)}

        def prepare_filename(self, info):
            return str(big)

    monkeypatch.setattr(engine.yt_dlp, "YoutubeDL", _FakeYDL)
    monkeypatch.setattr(engine, "DOWNLOADS", tmp_path)

    # Make every Path.stat report a > 4 GB file so the guard triggers.
    class _FakeStat:
        st_size = 5 * 1024 ** 3

    monkeypatch.setattr(engine.Path, "stat", lambda self, *a, **k: _FakeStat())

    with pytest.raises(Exception) as exc:
        engine.download_media("https://example.com/big")
    assert "4 GB" in str(exc.value)


# ===== Admin SSE feed =====
def test_admin_events_sse(client):
    _setup_admin(client)
    r = client.get("/admin/events")
    assert r.status_code == 200
    assert "text/event-stream" in r.content_type


# ===== Link history =====
def test_links_recorded_on_info_and_listed(client, monkeypatch):
    from neo.blueprints import api as _api

    def fake_info(url, cookiefile=None):
        return {"title": "Demo", "url": url}
    monkeypatch.setattr(_api, "fetch_info", fake_info)

    # A paste/view records a link.
    r = client.post("/info", json={"url": "https://example.com/clip"})
    assert r.status_code == 200
    assert r.get_json()["success"] is True

    # Login-free dev admin is unavailable here; the links endpoint is gated,
    # so check the DB directly via the adapter.
    from neo.db_adapter import get_db
    rows = get_db().execute(
        "SELECT url, action FROM links WHERE url=?", ("https://example.com/clip",)
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["action"] == "view"


def test_admin_links_endpoint_ready(client):
    # The /admin/links route must exist (gated). We just assert it responds
    # (401 unauthorized is fine — it proves the route is wired).
    r = client.get("/admin/links")
    assert r.status_code in (200, 401, 302)


# ===== Admin setup lock =====
def test_admin_setup_required_without_password(client, monkeypatch):
    # When no ADMIN_PASSWORD and no stored hash, /admin/login must redirect
    # to the setup page instead of opening the panel.
    monkeypatch.setattr(
        "neo.blueprints.admin.get_admin_password", lambda: None
    )
    r = client.get("/admin/login")
    assert r.status_code in (301, 302)
    assert "/admin/setup" in r.headers.get("Location", "")


def test_admin_setup_sets_password(client, monkeypatch):
    monkeypatch.setattr(
        "neo.blueprints.admin.get_admin_password", lambda: None
    )
    from neo.db_adapter import get_db
    get_db().execute("DELETE FROM settings WHERE key='admin_password_hash'")
    get_db().commit()
    r = client.post("/admin/setup", json={"password": "secret123"})
    assert r.status_code == 200
    assert r.get_json()["success"] is True
    # After setup, the gate should now report a password is configured.
    from neo.db_adapter import get_db
    row = get_db().execute(
        "SELECT value FROM settings WHERE key='admin_password_hash'"
    ).fetchone()
    assert row is not None
    assert row["value"].startswith(("pbkdf2:", "scrypt:"))


def test_admin_setup_blocked_once_password_set(client, monkeypatch):
    # Once a password is configured, an unauthenticated caller cannot use
    # /admin/setup to set/overwrite it.
    monkeypatch.setattr(
        "neo.blueprints.admin.get_admin_password", lambda: "preexistinghash"
    )
    r = client.post("/admin/setup", json={"password": "hacked"})
    assert r.status_code in (301, 302)
    assert "/admin/login" in r.headers.get("Location", "")


# ===== God mode + preset passthrough =====
def test_download_god_mode_preset(monkeypatch, tmp_path):
    """god_mode + preset are forwarded into the yt-dlp options."""
    from neo.core import engine

    captured = {}

    class _FakeYDL:
        def __init__(self, opts, *a, **k):
            captured.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=True):
            captured["url"] = url
            return {"title": "God", "ext": "mp4", "_filename": str(tmp_path / "god.mp4")}

        def prepare_filename(self, info):
            return str(tmp_path / "god.mp4")

    monkeypatch.setattr(engine.yt_dlp, "YoutubeDL", _FakeYDL)
    monkeypatch.setattr(engine, "DOWNLOADS", tmp_path)
    (tmp_path / "god.mp4").write_bytes(b"\0" * 10)

    engine.download_media(
        "https://example.com/god", mode="video",
        god_mode=True, preset="4k",
    )

    assert captured.get("concurrent_fragment_downloads") == 32
    assert captured.get("retries") == 10
    assert captured.get("external_downloader") == "aria2c"
    assert "height<=2160" in captured.get("format", "")
    assert captured.get("merge_output_format") == "mkv"


def test_remove_watermark_god_mode_adds_zones(monkeypatch, tmp_path):
    """god_mode stacks more delogo zones than normal mode."""
    import subprocess
    from neo.core import processor

    monkeypatch.setattr(processor, "DOWNLOADS", tmp_path)
    src = tmp_path / "vid.mp4"
    src.write_bytes(b"\0" * 10)

    last_cmd = {}

    def fake_run(cmd, *a, **k):
        last_cmd["cmd"] = list(cmd)
        # Create the output file so the processor call succeeds.
        Path(cmd[-1]).write_bytes(b"\0" * 10)
        class _R:
            stderr = None
        return _R()

    monkeypatch.setattr(subprocess, "run", fake_run)

    def count_delogo(cmd):
        # The -vf value is passed as a single arg: "delogo=...:show=0,delogo=..."
        if "-vf" in cmd:
            vf = cmd[cmd.index("-vf") + 1]
            return vf.count("delogo=")
        return 0

    # god_mode path
    processor.remove_watermark("vid.mp4", auto=True, god_mode=True)
    god_zones = count_delogo(last_cmd["cmd"])
    # normal path
    processor.remove_watermark("vid.mp4", auto=True, god_mode=False)
    normal_zones = count_delogo(last_cmd["cmd"])
    assert god_zones > normal_zones


# ===== Metadata erasure =====
def test_erase_metadata_wipes(monkeypatch, tmp_path):
    import subprocess
    from neo.core import processor

    monkeypatch.setattr(processor, "DOWNLOADS", tmp_path)
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"\0" * 10)

    ran = {}

    def fake_run(cmd, *a, **k):
        ran["args"] = cmd
        # Create the expected output file so the call succeeds.
        out_arg = cmd[-1]
        Path(out_arg).write_bytes(b"\0" * 10)
        class _R:
            stderr = None
        return _R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = processor.erase_metadata("clip.mp4")
    assert "wiped" in out["filename"]
    args = ran["args"]
    assert "-map_metadata" in args and "-1" in args
    assert "-fflags" in args and "+bitexact" in args


def test_wipe_route(client, monkeypatch, tmp_path):
    """POST /wipe erases metadata and returns a downloadable file name."""
    import subprocess
    from neo.core import processor

    monkeypatch.setattr(processor, "DOWNLOADS", tmp_path)
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"\0" * 10)

    def fake_run(cmd, *a, **k):
        Path(cmd[-1]).write_bytes(b"\0" * 10)
        class _R:
            stderr = None
        return _R()

    monkeypatch.setattr(subprocess, "run", fake_run)

    r = client.post("/wipe", json={"filename": "clip.mp4"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    assert "wiped" in body["filename"]
    assert body["download_url"].startswith("/serve/")


def test_wipe_route_requires_filename(client):
    r = client.post("/wipe", json={})
    assert r.status_code == 400
    assert r.get_json()["success"] is False


def test_batch_forwards_god_mode(monkeypatch, tmp_path):
    """god_mode/preset reach download_media via download_batch."""
    from neo.core import engine

    captured = {}

    class _FakeYDL:
        def __init__(self, opts, *a, **k):
            captured.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=True):
            return {"title": "B", "ext": "mp4", "_filename": str(tmp_path / "b.mp4")}

        def prepare_filename(self, info):
            return str(tmp_path / "b.mp4")

    monkeypatch.setattr(engine.yt_dlp, "YoutubeDL", _FakeYDL)
    monkeypatch.setattr(engine, "DOWNLOADS", tmp_path)
    (tmp_path / "b.mp4").write_bytes(b"\0" * 10)
    # Stub tasks so no real thread registry is needed for the unit check.
    import neo.core.tasks as tasks
    monkeypatch.setattr(tasks, "create_task", lambda fn, *a, **k: (fn(*a, **k), "tid")[1])
    monkeypatch.setattr(tasks, "get_task_status", lambda tid: {"status": "completed", "result": None})

    results = engine.download_batch(
        ["https://example.com/1"], god_mode=True, preset="audio",
    )
    assert captured.get("concurrent_fragment_downloads") == 32
    assert captured.get("merge_output_format") == "mp3"


# ===== Cookie plumbing =====
def test_apply_cookies_env_var(monkeypatch, tmp_path):
    """YTDLP_COOKIES env var is written to a temp cookiefile and applied."""
    from neo.core import engine

    monkeypatch.delenv("YTDLP_COOKIES", raising=False)
    monkeypatch.setenv("YTDLP_COOKIES", "# Netscape\nyoutube.com\tTRUE\t/\tTRUE\t0\tX\tY\n")
    opts = engine._apply_cookies({})
    assert "cookiefile" in opts
    content = Path(opts["cookiefile"]).read_text()
    assert "youtube.com" in content


def test_apply_cookies_explicit_override(monkeypatch, tmp_path):
    """An explicit cookiefile path always wins over the env var."""
    from neo.core import engine

    monkeypatch.setenv("YTDLP_COOKIES", "# Netscape\nyoutube.com\tTRUE\t/\tTRUE\t0\tX\tY\n")
    explicit = tmp_path / "mine.txt"
    explicit.write_text("youtube.com\tTRUE\t/\tTRUE\t0\tEXPLICIT\tZ\n")
    opts = engine._apply_cookies({}, cookiefile=str(explicit))
    assert opts["cookiefile"] == str(explicit)


def test_apply_cookies_no_env(monkeypatch):
    """With no cookies available, no cookiefile key is set."""
    from neo.core import engine

    monkeypatch.delenv("YTDLP_COOKIES", raising=False)
    # Ensure no cookies.txt exists at the resolved project root for this test.
    opts = engine._apply_cookies({})
    assert "cookiefile" not in opts


# ===== Terabox TeraPlayer =====
def test_terabox_extractor_registered(monkeypatch):
    """The custom TeraboxIE is injected into yt-dlp's registry."""
    import yt_dlp.extractor as extractor_mod
    from neo.core.extractors.terabox import TeraboxIE, register
    # Ensure registration lands in the live registry even if a prior
    # import_extractors() rebuilt the dict.
    extractor_mod.import_extractors()
    register()
    ctx = extractor_mod._extractors_context.value
    assert ctx.get('terabox') is TeraboxIE


def test_terabox_url_matching():
    """Mirror hosts and both URL shapes route to the TeraboxIE."""
    from neo.core.extractors.terabox import TeraboxIE
    good = [
        "https://1024terabox.com/s/1slzi40Hk5XJq9TWyl8l9BQ",
        "https://www.terabox.app/sharing/link?surl=slzi40Hk5XJq9TWyl8l9BQ",
        "https://terabox.com/s/abcDEF123",
        "https://dubox.com/s/xyz789",
    ]
    for u in good:
        assert TeraboxIE.suitable(u), f"should match: {u}"
    assert not TeraboxIE.suitable("https://youtube.com/watch?v=abc")


def test_terabox_resolve_happy_path(monkeypatch):
    """resolve_terabox scrapes jsToken, calls share/list, returns dlink."""
    from neo.core.extractors import terabox as mod

    def fake_get(url, headers, timeout=20):
        if '/s/' in url or '/sharing' in url:
            return "<html>var jsToken = 'TOK123';</html>"
        if '/share/list' in url:
            assert 'jsToken=TOK123' in url
            return '{"errno":0,"list":[{"server_filename":"clip.mp4","size":12345,"dlink":"https://dl.terabox.com/f"}]}'
        return ''

    monkeypatch.setattr(mod, '_http_get', fake_get)
    res = mod.resolve_terabox("https://1024terabox.com/s/1slzi40Hk5XJq9TWyl8l9BQ")
    assert res['title'] == 'clip.mp4'
    assert res['ext'] == 'mp4'
    assert res['filesize'] == 12345
    assert res['url'].startswith('https://dl.terabox.com/')


def test_terabox_resolve_empty_list_errors(monkeypatch):
    """An empty file list yields a clear ValueError, not a crash."""
    from neo.core.extractors import terabox as mod

    def fake_get(url, headers, timeout=20):
        if '/s/' in url or '/sharing' in url:
            return "var jsToken = 'T';"
        if '/share/list' in url:
            return '{"errno":0,"list":[]}'
        return ''

    monkeypatch.setattr(mod, '_http_get', fake_get)
    with pytest.raises(ValueError):
        mod.resolve_terabox("https://terabox.com/s/abc")


def test_terabox_resolve_login_required_errors(monkeypatch):
    """errno=2 (login) is reported as a session-required error."""
    from neo.core.extractors import terabox as mod

    def fake_get(url, headers, timeout=20):
        if '/s/' in url or '/sharing' in url:
            return "var jsToken = 'T';"
        if '/share/list' in url:
            return '{"errno":2,"errmsg":"login required"}'
        return ''

    monkeypatch.setattr(mod, '_http_get', fake_get)
    with pytest.raises(ValueError) as e:
        mod.resolve_terabox("https://terabox.com/s/abc")
    assert 'logged-in' in str(e.value).lower()


def test_terabox_resolve_route(client, monkeypatch):
    """/terabox/resolve returns the dlink JSON to the client."""
    from neo.core.extractors import terabox as mod

    def fake_get(url, headers, timeout=20):
        if '/s/' in url or '/sharing' in url:
            return "var jsToken = 'T';"
        if '/share/list' in url:
            return '{"errno":0,"list":[{"server_filename":"movie.mp4","size":999,"dlink":"https://dl.terabox.com/x"}]}'
        return ''

    monkeypatch.setattr(mod, '_http_get', fake_get)
    r = client.post('/terabox/resolve', json={'url': 'https://terabox.com/s/abc'})
    assert r.status_code == 200
    d = r.get_json()
    assert d['success'] is True
    assert d['direct_url'] == 'https://dl.terabox.com/x'
    assert d['title'] == 'movie.mp4'


def test_terabox_resolve_rejects_non_terabox(client):
    """Non-Terabox URLs are rejected by the resolver route."""
    r = client.post('/terabox/resolve', json={'url': 'https://youtube.com/watch?v=1'})
    assert r.status_code == 400
    assert r.get_json()['success'] is False
