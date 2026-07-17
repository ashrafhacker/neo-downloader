import sys, os
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(str(ROOT))

try:
    from neo.wsgi import app
    handler = app
except Exception as e:
    import traceback
    err_detail = traceback.format_exc()
    from flask import Flask, jsonify
    app = Flask(__name__)
    @app.route('/<path:path>')
    @app.route('/')
    def catch_all(path=''):
        return jsonify({"error": f"neo app failed to load: {str(e)}", "detail": err_detail}), 500
    handler = app
