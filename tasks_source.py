"""Read and prepare the task list from tasks.json and optional Asana cache."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo


def _sort_key(task):
    priority = task.get("priority")
    return (task.get("due") or "", priority if priority is not None else 99)


def get_tasks(config, extra_tasks=None):
    """Return incomplete tasks grouped into Upcoming / Overdue / No Due Date.

    extra_tasks: pre-fetched list of task dicts (e.g. from Asana cache) merged
    with tasks.json before sorting. Pass None or [] to skip.

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

    incomplete = [dict(t) for t in file_tasks + list(extra_tasks or []) if not t.get("done")]

    upcoming, overdue, no_due = [], [], []
    for task in incomplete:
        due = task.get("due")
        is_overdue = False
        if due:
            try:
                due_dt = datetime.fromisoformat(due)
                if due_dt.tzinfo is None:
                    due_dt = due_dt.replace(tzinfo=tz)
                is_overdue = due_dt < now
            except ValueError:
                pass
        task["overdue"] = is_overdue

        if not due:
            no_due.append(task)
        elif is_overdue:
            overdue.append(task)
        else:
            upcoming.append(task)

    upcoming.sort(key=_sort_key)
    overdue.sort(key=_sort_key)
    no_due.sort(key=_sort_key)

    sections = []
    if upcoming:
        sections.append({"name": "Upcoming", "tasks": upcoming})
    if overdue:
        sections.append({"name": "Overdue", "tasks": overdue})
    if no_due:
        sections.append({"name": "No Due Date", "tasks": no_due})

    return {
        "sections": sections,
        "error": file_error,
    }
