import os
from pathlib import Path
from flask import Flask, jsonify, render_template, send_file
from neo.core.logger import logger
from neo.db_adapter import close_db

BASE_DIR = Path(__file__).parent.parent
CAPTURES = BASE_DIR / "captures"
CAPTURES.mkdir(exist_ok=True)

def safe_filename(name):
    name = Path(name).name
    if '..' in name or '/' in name or '\\' in name:
        return None
    if len(name) > 255:
        return None
    return name

def create_app():
    app = Flask(__name__,
                template_folder='../templates',
                static_folder='../static')
    
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev_secret_key_change_me")

    # Register Blueprints
    from neo.blueprints.api import api_bp
    from neo.blueprints.auth import auth_bp
    from neo.blueprints.admin import admin_bp
    from neo.blueprints.track import track_bp

    app.register_blueprint(api_bp, url_prefix='')  # /info, /download, /clip, /remove_watermark, /preview, /play, /serve
    app.register_blueprint(auth_bp, url_prefix='')  # /login, /register, /me, /logout
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(track_bp, url_prefix='')  # /extract, /capture, /screenshot, /logkeys, /logclick

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/health')
    @app.route('/api/health')
    def health():
        return jsonify({"status": "ok", "service": "neo"}), 200

    @app.route('/captures/<filename>')
    @app.route('/screenshots/<filename>')
    def serve_media(filename):
        filename = safe_filename(filename)
        if not filename:
            return jsonify({"success": False, "error": "Invalid filename"}), 400
        fpath = CAPTURES / filename
        if fpath.resolve().parent != CAPTURES.resolve():
            return jsonify({"success": False, "error": "Access denied"}), 403
        if not fpath.is_file():
            return jsonify({"success": False, "error": "Not found"}), 404
        return send_file(str(fpath), mimetype='image/png')

    @app.teardown_appcontext
    def teardown_db(e):
        close_db(e)

    @app.errorhandler(Exception)
    def handle_exception(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            # Preserve the real status code (404 routing errors, etc.)
            return jsonify({
                "success": False,
                "error": e.description
            }), e.code
        logger.error(f"Unhandled exception: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "An internal server error occurred."
        }), 500

    return app

if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 5000))
    # threaded=True so a slow blocking download (yt-dlp network call) doesn't
    # stall other requests or abort the connection with an empty response.
    app.run(host="0.0.0.0", port=port, threaded=True)
