"""Flask server: serves the kiosk frontend and a small JSON API."""

import os
import threading
import time
from datetime import datetime

import yaml
from flask import Flask, jsonify, send_from_directory
from zoneinfo import ZoneInfo

import asana_source
import calendar_source
import tasks_source

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(__name__, static_folder=None)

_config = None

_events_cache = {"data": None}
_events_lock = threading.Lock()

_tasks_cache = {"tasks": [], "error": None}
_tasks_lock = threading.Lock()


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------- Refresh functions (never raise; store errors in cache) ----------

def refresh_events():
    try:
        data = calendar_source.get_events(_config)
    except Exception as exc:
        data = {"events": [], "stale": True, "stale_since": None, "errors": [str(exc)]}
    with _events_lock:
        _events_cache["data"] = data


def refresh_asana():
    try:
        tasks, error = asana_source.fetch_tasks(_config["asana"])
    except Exception as exc:
        tasks, error = [], str(exc)
    with _tasks_lock:
        _tasks_cache["tasks"] = tasks
        _tasks_cache["error"] = error


def _refresh_loop(refresh_fn, config_key, default_minutes):
    try:
        interval = max(1, int(_config.get(config_key, default_minutes))) * 60
    except (ValueError, TypeError):
        interval = default_minutes * 60
    while True:
        refresh_fn()
        time.sleep(interval)


# ---------- Routes ----------

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
        "eink_mode": bool(_config.get("eink_mode", False)),
    })


@app.route("/api/tasks")
def api_tasks():
    with _tasks_lock:
        extra = list(_tasks_cache["tasks"])
        asana_error = _tasks_cache["error"]

    result = tasks_source.get_tasks(_config, extra_tasks=extra)
    result["error"] = "; ".join(filter(None, [result.get("error"), asana_error])) or None
    return jsonify(result)


# ---------- Startup ----------

def _ensure_tasks_file():
    path = _config.get("tasks_file", "data/tasks.json")
    if not os.path.isabs(path):
        path = os.path.join(BASE_DIR, path)
        _config["tasks_file"] = path
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("[]\n")


def create_app():
    global _config
    _config = load_config()
    _ensure_tasks_file()

    threading.Thread(
        target=_refresh_loop, args=(refresh_events, "calendar_refresh_minutes", 10), daemon=True
    ).start()

    if _config.get("asana", {}).get("enabled"):
        threading.Thread(
            target=_refresh_loop, args=(refresh_asana, "tasks_refresh_minutes", 5), daemon=True
        ).start()

    return app


if __name__ == "__main__":
    flask_app = create_app()
    flask_app.run(host="0.0.0.0", port=_config.get("port", 8080))
