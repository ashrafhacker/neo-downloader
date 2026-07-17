"""Per-user API token issuance and lookup for programmatic access."""
import secrets
from neo.db_adapter import get_db


def generate_token():
    return "neo_" + secrets.token_urlsafe(32)


def get_token(user):
    """Return the user's current API token, creating one if absent."""
    db = get_db()
    rows = list(db.execute("SELECT api_token FROM users WHERE username=?", (user,)))
    if not rows:
        return None
    token = rows[0]["api_token"]
    if not token:
        token = generate_token()
        db.execute("UPDATE users SET api_token=? WHERE username=?", (token, user))
        db.commit()
    return token


def rotate_token(user):
    token = generate_token()
    db = get_db()
    db.execute("UPDATE users SET api_token=? WHERE username=?", (token, user))
    db.commit()
    return token


def user_for_token(token):
    """Resolve a username from a raw API token, or None."""
    if not token:
        return None
    db = get_db()
    rows = list(db.execute("SELECT username FROM users WHERE api_token=?", (token,)))
    return rows[0]["username"] if rows else None
