import sys, os, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.chdir(str(Path(__file__).parent.parent))

try:
    from app import app as _app
    app = _app
except Exception as e:
    import traceback
    err_detail = traceback.format_exc()
    from flask import Flask, jsonify
    app = Flask(__name__)
    @app.route('/<path:path>')
    @app.route('/')
    def catch_all(path=''):
        return jsonify({"error": f"App failed to load: {str(e)}", "detail": err_detail, "fix": "Check server logs"}), 500
handler = app
