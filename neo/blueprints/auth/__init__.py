from flask import Blueprint, request, jsonify, session, render_template
from werkzeug.security import generate_password_hash, check_password_hash
from neo.db_adapter import get_db
from neo.core.auth_tokens import get_token, rotate_token
import datetime

auth_bp = Blueprint('auth', __name__)


@auth_bp.route("/login", methods=["GET"])
def login_page():
    """Render the app (with its login modal) for redirected anonymous users."""
    return render_template("index.html")

@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    
    if not username or not email or not password:
        return jsonify({"success": False, "error": "Missing fields"}), 400
        
    db = get_db()
    # Check existing
    existing = db.execute("SELECT id FROM users WHERE username=? OR email=?", (username, email))
    if list(existing):
        return jsonify({"success": False, "error": "Username or email already taken"}), 409
        
    pwd_hash = generate_password_hash(password)
    now = datetime.datetime.now().isoformat()
    db.execute("INSERT INTO users(username,email,password_hash,created_at,last_login,is_active,download_limit) VALUES(?,?,?,?,?,?,?)",
        (username, email, pwd_hash, now, now, 1, -1))
    db.commit()
    
    session['user_id'] = username
    return jsonify({"success": True, "message": "Account created!", "user": username})

@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    
    db = get_db()
    rows = db.execute("SELECT * FROM users WHERE username=? OR email=?", (username, username))
    user = list(rows)
    user = user[0] if user else None
    
    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({"success": False, "error": "Invalid username or password"}), 401
        
    now = datetime.datetime.now().isoformat()
    db.execute("UPDATE users SET last_login=? WHERE username=?", (now, user['username']))
    db.commit()
    
    session['user_id'] = user['username']
    return jsonify({"success": True, "message": f"Welcome back, {user['username']}!", "user": user['username']})

@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.pop('user_id', None)
    return jsonify({"success": True})

@auth_bp.route("/me")
def me():
    username = session.get('user_id')
    if not username:
        return jsonify({"authenticated": False})
        
    db = get_db()
    rows = db.execute("SELECT username,email,created_at,last_login,download_limit FROM users WHERE username=?", (username,))
    user = list(rows)
    user = user[0] if user else None
    
    if not user:
        session.pop('user_id', None)
        return jsonify({"authenticated": False})
        
    return jsonify({
        "authenticated": True,
        "user": dict(user)
    })


@auth_bp.route("/token", methods=["GET"])
def token_status():
    """Show the current user's API token (creates one if absent)."""
    username = session.get('user_id')
    if not username:
        return jsonify({"success": False, "error": "Not authenticated"}), 401
    return jsonify({"success": True, "token": get_token(username)})


@auth_bp.route("/token/rotate", methods=["POST"])
def token_rotate():
    """Issue a new API token, invalidating the old one."""
    username = session.get('user_id')
    if not username:
        return jsonify({"success": False, "error": "Not authenticated"}), 401
    return jsonify({"success": True, "token": rotate_token(username)})
