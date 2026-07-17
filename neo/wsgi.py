"""WSGI entry point for the neo application.

gunicorn invocation:  gunicorn neo.wsgi:app --bind 0.0.0.0:$PORT
"""
import os
from pathlib import Path

# Ensure the project root is importable and is the working directory so that
# relative paths (downloads/, captures/, templates/, logs/) resolve correctly.
ROOT = Path(__file__).parent.parent
os.chdir(ROOT)
if str(ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(ROOT))

from neo.app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
