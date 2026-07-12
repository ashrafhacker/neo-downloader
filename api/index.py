import sys, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.chdir(str(Path(__file__).parent.parent))

from app import app

# Vercel Python serverless handler
handler = app
