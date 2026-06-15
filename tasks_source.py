"""Read and prepare the task list from tasks.json."""

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


def get_tasks(config):
    """Read tasks_file and return incomplete tasks grouped by section.

    Returns a dict:
      {
        "sections": [ {"name": str, "tasks": [task, ...]}, ... ],
        "error": str | None,
      }
    Each task gains an "overdue" boolean based on the current time.
    """
    tz = ZoneInfo(config["timezone"])
    now = datetime.now(tz)
    path = config.get("tasks_file", "data/tasks.json")

    try:
        with open(path, "r", encoding="utf-8") as f:
            tasks = json.load(f)
    except (OSError, ValueError) as exc:
        return {"sections": [], "error": str(exc)}

    incomplete = [t for t in tasks if not t.get("done")]

    for task in incomplete:
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

    incomplete.sort(key=_sort_key)

    sections = []
    order = []
    by_section = {}
    for task in incomplete:
        section = task.get("section", "Other")
        if section not in by_section:
            by_section[section] = []
            order.append(section)
        by_section[section].append(task)

    for name in order:
        sections.append({"name": name, "tasks": by_section[name]})

    return {"sections": sections, "error": None}
