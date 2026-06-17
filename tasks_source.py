"""Read and prepare the task list from tasks.json and optional Asana cache."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo


def _sort_key(task):
    due = task.get("due")
    priority = task.get("priority")
    return (
        0 if due else 1,
        due or "",
        priority if priority is not None else 99,
    )


def _add_overdue(task, now, tz):
    due = task.get("due")
    overdue = False
    if due:
        try:
            due_dt = datetime.fromisoformat(due)
            if due_dt.tzinfo is None:
                due_dt = due_dt.replace(tzinfo=tz)
            overdue = due_dt < now
        except ValueError:
            pass
    task["overdue"] = overdue


def get_tasks(config, extra_tasks=None):
    """Return incomplete tasks grouped by section, sorted by due then priority.

    extra_tasks: pre-fetched list of task dicts (e.g. from Asana cache) that
    are merged with tasks.json before sorting. Pass None or [] to skip.

    Returns:
      {
        "sections": [ {"name": str, "tasks": [task, ...]}, ... ],
        "error": str | None,
      }
    """
    tz = ZoneInfo(config["timezone"])
    now = datetime.now(tz)
    path = config.get("tasks_file", "data/tasks.json")

    file_tasks = []
    file_error = None
    try:
        with open(path, "r", encoding="utf-8") as f:
            file_tasks = json.load(f)
    except (OSError, ValueError) as exc:
        file_error = str(exc)

    all_tasks = file_tasks + list(extra_tasks or [])
    incomplete = [t for t in all_tasks if not t.get("done")]

    for task in incomplete:
        _add_overdue(task, now, tz)

    incomplete.sort(key=_sort_key)

    order = []
    by_section = {}
    for task in incomplete:
        section = task.get("section", "Other")
        if section not in by_section:
            by_section[section] = []
            order.append(section)
        by_section[section].append(task)

    sections = [{"name": name, "tasks": by_section[name]} for name in order]

    return {"sections": sections, "error": file_error}
