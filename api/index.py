import sys, os, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.chdir(str(Path(__file__).parent.parent))

try:
    from app import app
    handler = app
except Exception as e:
    from flask import Flask, jsonify
    app = Flask(__name__)
    @app.route('/<path:path>')
    @app.route('/')
    def catch_all(path=''):
        return jsonify({"error": f"App failed to load: {str(e)}", "fix": "Check server logs"}), 500
    handler = app
