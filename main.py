"""Entry point to run the Vocal Isolator web app."""

import os

from app import app

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "").strip().lower() in ("1", "true", "yes")
    app.run(host="0.0.0.0", port=8001, debug=debug)
