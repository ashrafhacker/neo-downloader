"""Root WSGI entry point.

Delegates to the neo application so existing deployment tooling
(Procfile `gunicorn app:app`, Vercel, Netlify) keeps working.
"""
import os
from pathlib import Path

ROOT = Path(__file__).parent
os.chdir(ROOT)
if str(ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(ROOT))

try:
    from neo.wsgi import app
except Exception as e:  # pragma: no cover - fallback for import failures
    import traceback
    from flask import Flask, jsonify
    app = Flask(__name__)

    @app.route("/<path:path>")
    @app.route("/")
    def _fail(path=""):
        return jsonify({
            "error": f"neo app failed to load: {e}",
            "detail": traceback.format_exc(),
        }), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
