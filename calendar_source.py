"""Fetch, cache, and parse ICS calendar feeds for today's events."""

import json
import os
import re
from datetime import datetime, date, time, timedelta

import requests
import recurring_ical_events
from icalendar import Calendar
from zoneinfo import ZoneInfo

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
STATE_FILE = os.path.join(CACHE_DIR, "state.json")
FETCH_TIMEOUT = 15


def _safe_name(name):
    return re.sub(r"[^A-Za-z0-9_-]", "_", name)


def _cache_path(name):
    return os.path.join(CACHE_DIR, f"{_safe_name(name)}.ics")


def _load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_state(state):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)


def _fetch_ics(url):
    resp = requests.get(url, timeout=FETCH_TIMEOUT)
    resp.raise_for_status()
    return resp.content


def _to_local(value, tzinfo):
    """Normalize a date/datetime from icalendar to a tz-aware datetime in tzinfo."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=tzinfo)
        return value.astimezone(tzinfo)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=tzinfo)
    raise TypeError(f"Unsupported date type: {type(value)!r}")


def _is_all_day(component):
    dtstart = component.get("dtstart")
    return dtstart is not None and not isinstance(dtstart.dt, datetime)


def get_events(config):
    """Fetch all configured calendars and return today's merged events.

    Returns a dict:
      {
        "events": [ {start, end, title, source, color, all_day}, ... ],
        "stale": bool,
        "stale_since": ISO8601 str or None,
        "errors": [ "Source: message", ... ],
      }
    """
    tz = ZoneInfo(config["timezone"])
    now_local = datetime.now(tz)
    day_start = datetime.combine(now_local.date(), time.min, tzinfo=tz)
    day_end = day_start + timedelta(days=1)

    state = _load_state()
    events = []
    errors = []
    any_stale = False
    oldest_stale = None

    os.makedirs(CACHE_DIR, exist_ok=True)

    for cal in config.get("calendars", []):
        name = cal["name"]
        color = cal.get("color", "#888888")
        raw = None
        is_stale = False

        try:
            raw = _fetch_ics(cal["ics_url"])
            with open(_cache_path(name), "wb") as f:
                f.write(raw)
            state[name] = {"last_success": now_local.isoformat()}
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            try:
                with open(_cache_path(name), "rb") as f:
                    raw = f.read()
                is_stale = True
                any_stale = True
            except OSError:
                raw = None

        if raw is None:
            continue

        if is_stale:
            last_success = state.get(name, {}).get("last_success")
            if last_success:
                ts = datetime.fromisoformat(last_success)
                if oldest_stale is None or ts < oldest_stale:
                    oldest_stale = ts

        try:
            calendar = Calendar.from_ical(raw)
            occurrences = recurring_ical_events.of(calendar).between(day_start, day_end)
        except Exception as exc:
            errors.append(f"{name}: parse error: {exc}")
            continue

        for component in occurrences:
            try:
                all_day = _is_all_day(component)
                start = _to_local(component["dtstart"].dt, tz)
                if "dtend" in component:
                    end = _to_local(component["dtend"].dt, tz)
                else:
                    end = start + timedelta(hours=1)

                title = str(component.get("summary", "(no title)"))

                events.append({
                    "title": title,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "source": name,
                    "color": color,
                    "all_day": all_day,
                })
            except Exception as exc:
                errors.append(f"{name}: event error: {exc}")

    _save_state(state)

    events.sort(key=lambda e: (e["start"], e["end"]))

    return {
        "events": events,
        "stale": any_stale,
        "stale_since": oldest_stale.isoformat() if oldest_stale else None,
        "errors": errors,
    }
