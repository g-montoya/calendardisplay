"""Fetch tasks from the Asana REST API and map them to the task schema."""

from datetime import datetime

import requests

BASE_URL = "https://app.asana.com/api/1.0"
FETCH_TIMEOUT = 15

_PRIORITY_MAP = {
    "high": 1,
    "urgent": 1,
    "medium": 2,
    "normal": 2,
    "low": 3,
}

_OPT_FIELDS = (
    "gid,name,due_on,due_at,completed,"
    "custom_fields,custom_fields.name,custom_fields.type,"
    "custom_fields.enum_value,custom_fields.enum_value.name"
)


def _get(token, url, params=None):
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        params=params,
        timeout=FETCH_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _project_name(token, project_id):
    return _get(token, f"{BASE_URL}/projects/{project_id}", {"opt_fields": "name"})["data"]["name"]


def _project_tasks(token, project_id):
    tasks = []
    params = {"project": project_id, "opt_fields": _OPT_FIELDS, "completed_since": "now", "limit": 100}
    while True:
        body = _get(token, f"{BASE_URL}/tasks", params)
        tasks.extend(body["data"])
        next_page = body.get("next_page")
        if not next_page:
            break
        params["offset"] = next_page["offset"]
    return tasks


def _normalize_due(raw_task):
    due_at = raw_task.get("due_at")
    if due_at:
        try:
            return datetime.fromisoformat(due_at.replace("Z", "+00:00")).isoformat()
        except ValueError:
            pass
    return raw_task.get("due_on")


def _parse_priority(custom_fields):
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
        pid = str(project_id)
        try:
            name = _project_name(token, pid)
            for raw in _project_tasks(token, pid):
                all_tasks.append(_map_task(raw, name))
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            errors.append(f"Asana project {pid}: HTTP {status}")
        except Exception as exc:
            errors.append(f"Asana project {pid}: {exc}")

    return all_tasks, ("; ".join(errors) if errors else None)
