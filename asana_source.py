"""Fetch tasks from the Asana REST API and map them to the task schema."""

from datetime import datetime, timezone

import requests

BASE_URL = "https://app.asana.com/api/1.0"
FETCH_TIMEOUT = 15

# Asana enum priority names → our 1-3 priority scale
_PRIORITY_MAP = {
    "high": 1,
    "urgent": 1,
    "medium": 2,
    "normal": 2,
    "low": 3,
}

# Fields requested from Asana on every task
_OPT_FIELDS = ",".join([
    "gid",
    "name",
    "due_on",
    "due_at",
    "completed",
    "custom_fields",
    "custom_fields.name",
    "custom_fields.type",
    "custom_fields.enum_value",
    "custom_fields.enum_value.name",
])


def _headers(token):
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _project_name(token, project_id):
    resp = requests.get(
        f"{BASE_URL}/projects/{project_id}",
        headers=_headers(token),
        params={"opt_fields": "name"},
        timeout=FETCH_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["data"]["name"]


def _project_tasks(token, project_id):
    """Fetch all incomplete tasks from one project, handling pagination."""
    tasks = []
    params = {
        "project": project_id,
        "opt_fields": _OPT_FIELDS,
        "completed_since": "now",  # only incomplete tasks
        "limit": 100,
    }
    while True:
        resp = requests.get(
            f"{BASE_URL}/tasks",
            headers=_headers(token),
            params=params,
            timeout=FETCH_TIMEOUT,
        )
        resp.raise_for_status()
        body = resp.json()
        tasks.extend(body["data"])
        next_page = body.get("next_page")
        if not next_page:
            break
        params["offset"] = next_page["offset"]
    return tasks


def _normalize_due(raw_task):
    """Return a consistent ISO-8601 string (or None) from Asana's due fields."""
    due_at = raw_task.get("due_at")   # datetime string, may end in ".000Z"
    due_on = raw_task.get("due_on")   # date string "YYYY-MM-DD" or None

    if due_at:
        try:
            dt = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
            return dt.isoformat()
        except ValueError:
            pass

    return due_on  # "YYYY-MM-DD" string, or None


def _parse_priority(custom_fields):
    """Return 1-3 from the first enum custom field named 'priority', else None."""
    for cf in custom_fields or []:
        if cf.get("type") == "enum" and "priority" in (cf.get("name") or "").lower():
            val = ((cf.get("enum_value") or {}).get("name") or "").lower()
            if val in _PRIORITY_MAP:
                return _PRIORITY_MAP[val]
    return None


def _map_task(raw, section):
    return {
        "id": f"asana:{raw['gid']}",
        "title": raw["name"],
        "due": _normalize_due(raw),
        "section": section,
        "priority": _parse_priority(raw.get("custom_fields")),
        "done": raw.get("completed", False),
    }


def fetch_tasks(asana_config):
    """Fetch all tasks from configured Asana projects.

    Returns (tasks: list[dict], error: str | None).
    On partial failure the successfully fetched tasks are still returned.
    """
    token = asana_config.get("token", "").strip()
    project_ids = asana_config.get("project_ids") or []

    if not token:
        return [], "Asana token not configured"

    all_tasks = []
    errors = []

    for project_id in project_ids:
        try:
            name = _project_name(token, str(project_id))
            raw_tasks = _project_tasks(token, str(project_id))
            for raw in raw_tasks:
                all_tasks.append(_map_task(raw, name))
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            errors.append(f"Asana project {project_id}: HTTP {status}")
        except Exception as exc:
            errors.append(f"Asana project {project_id}: {exc}")

    return all_tasks, ("; ".join(errors) if errors else None)
