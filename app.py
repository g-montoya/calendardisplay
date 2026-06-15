"""Flask server: serves the kiosk frontend and a small JSON API."""

import os
import threading
import time
from datetime import datetime

import yaml
from flask import Flask, jsonify, send_from_directory
from zoneinfo import ZoneInfo

import calendar_source
import tasks_source

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(__name__, static_folder=None)

_config = None
_events_cache = {"data": None}
_events_lock = threading.Lock()


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def refresh_events():
    data = calendar_source.get_events(_config)
    with _events_lock:
        _events_cache["data"] = data


def refresh_loop():
    interval = max(1, int(_config.get("calendar_refresh_minutes", 10))) * 60
    while True:
        try:
            refresh_events()
        except Exception as exc:
            with _events_lock:
                _events_cache["data"] = {
                    "events": [],
                    "stale": True,
                    "stale_since": None,
                    "errors": [f"refresh failed: {exc}"],
                }
        time.sleep(interval)


@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(STATIC_DIR, filename)


@app.route("/api/events")
def api_events():
    with _events_lock:
        data = _events_cache["data"]
    if data is None:
        data = {"events": [], "stale": False, "stale_since": None, "errors": []}
    tz = ZoneInfo(_config["timezone"])
    return jsonify({
        **data,
        "now": datetime.now(tz).isoformat(),
        "working_hours_start": _config.get("working_hours_start", "06:00"),
        "working_hours_end": _config.get("working_hours_end", "22:00"),
    })


@app.route("/api/tasks")
def api_tasks():
    return jsonify(tasks_source.get_tasks(_config))


def create_app():
    global _config
    _config = load_config()
    refresh_events()
    thread = threading.Thread(target=refresh_loop, daemon=True)
    thread.start()
    return app


if __name__ == "__main__":
    flask_app = create_app()
    flask_app.run(host="0.0.0.0", port=_config.get("port", 8080))
