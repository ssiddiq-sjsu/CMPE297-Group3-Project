"""Configuration for the vacation planning server."""
import os

# Server port: set PORT environment variable to override (e.g. PORT=8080)
PORT = int(os.environ.get("PORT", 5000))
# Host: 127.0.0.1 = local only. Set LISTEN_ALL=1 or HOST=0.0.0.0 to listen on all interfaces.
LISTEN_ALL = os.environ.get("LISTEN_ALL", "").lower() in ("1", "true", "yes")
HOST = "0.0.0.0" if LISTEN_ALL else os.environ.get("HOST", "127.0.0.1")
DEBUG = os.environ.get("DEBUG", "false").lower() in ("1", "true", "yes")
