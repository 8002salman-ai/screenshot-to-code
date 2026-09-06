"""Vercel Python runtime entrypoint: serves the FastAPI app as an ASGI handler.

Exposes HTTP routes AND the /generate-code WebSocket route (Vercel Functions
serve WebSockets on Fluid compute; ASGI apps need no Vercel-specific upgrade
API — see https://vercel.com/docs/functions/websockets).
"""

import os
import sys

# The bundle root holds main.py/config.py/... ; make imports robust regardless
# of which directory the runtime puts on sys.path first.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402

handler = app
