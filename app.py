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

# Asana task cache: populated by background thread when asana.enabled is true.
_tasks_cache = {"tasks": [], "error": None}
_tasks_lock = threading.Lock()


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------- Calendar refresh ----------

def refresh_events():
    data = calendar_source.get_events(_config)
    with _events_lock:
        _events_cache["data"] = data


def calendar_refresh_loop():
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


# ---------- Asana task refresh ----------

def refresh_asana():
    tasks, error = asana_source.fetch_tasks(_config["asana"])
    with _tasks_lock:
        _tasks_cache["tasks"] = tasks
        _tasks_cache["error"] = error


def asana_refresh_loop():
    interval = max(1, int(_config.get("tasks_refresh_minutes", 5))) * 60
    while True:
        try:
            refresh_asana()
        except Exception as exc:
            with _tasks_lock:
                _tasks_cache["error"] = f"Asana refresh failed: {exc}"
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
    })


@app.route("/api/tasks")
def api_tasks():
    with _tasks_lock:
        extra = list(_tasks_cache["tasks"])
        asana_error = _tasks_cache["error"]

    result = tasks_source.get_tasks(_config, extra_tasks=extra)

    if asana_error and not result.get("error"):
        result["error"] = asana_error
    elif asana_error:
        result["error"] = f"{result['error']}; {asana_error}"

    return jsonify(result)


# ---------- Startup ----------

def _ensure_tasks_file():
    path = _config.get("tasks_file", "data/tasks.json")
    if not os.path.isabs(path):
        path = os.path.join(BASE_DIR, path)
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("[]\n")


def create_app():
    global _config
    _config = load_config()

    _ensure_tasks_file()

    refresh_events()
    threading.Thread(target=calendar_refresh_loop, daemon=True).start()

    asana_cfg = _config.get("asana") or {}
    if asana_cfg.get("enabled"):
        refresh_asana()
        threading.Thread(target=asana_refresh_loop, daemon=True).start()

    return app


if __name__ == "__main__":
    flask_app = create_app()
    flask_app.run(host="0.0.0.0", port=_config.get("port", 8080))
