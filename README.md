# Calendar Display

A self-hosted, always-on calendar + task wall display for a Raspberry Pi driving an
HDMI monitor (default layout: 1920x1080 landscape, fully responsive).

- **Left column:** today's events from multiple ICS calendars, merged onto a single
  vertical timeline with a live "now" line.
- **Right column:** current task list, grouped by section, read from `tasks.json`.

No AI/LLM. Deterministic display logic only. Backend is Flask; frontend is plain
HTML/CSS/JS with no build step.

## How it works

- `app.py` — Flask server. Serves `static/` and exposes:
  - `GET /api/events` — today's merged calendar events (cached, refreshed in the
    background every `calendar_refresh_minutes`)
  - `GET /api/tasks` — incomplete tasks grouped by section, read fresh from
    `tasks.json` on each request
- `calendar_source.py` — fetches each ICS feed, expands recurring events for today,
  converts everything to the configured timezone, and caches the last successful
  fetch to `cache/` so the display keeps working if the network drops.
- `tasks_source.py` — reads and sorts `tasks.json`.
- `static/` — the kiosk frontend (`index.html`, `style.css`, `app.js`).

## End-to-end flow

### 1. On your PC (development)

Make changes, then push to your private GitHub repo:

```bash
git add .
git commit -m "Update calendar display"
git push
```

### 2. On the Raspberry Pi (first-time setup, over SSH)

```bash
git clone <your-private-repo-url> CalendarDisplay
cd CalendarDisplay
cp config.example.yaml config.yaml
nano config.yaml   # fill in your ICS URLs, timezone, etc. (see below)
./setup.sh
sudo reboot
```

After reboot, the Pi boots into the desktop session, the `calendardisplay` systemd
service starts the Flask server, and Chromium opens full-screen in kiosk mode
showing `http://localhost:8080` (or whichever port you configured).

> The Pi's system timezone should match `timezone` in `config.yaml` (the displayed
> clock uses the browser/OS local time). Set it with `sudo raspi-config` (Localisation
> Options > Timezone) if needed.

### 3. Updating later

```bash
ssh pi@<your-pi>
cd CalendarDisplay
git pull
sudo systemctl restart calendardisplay
```

If `requirements.txt` changed, also run:

```bash
./venv/bin/pip install -r requirements.txt
```

## Configuration (`config.yaml`)

Copy `config.example.yaml` to `config.yaml` (this file is gitignored — never commit
it, since it contains your private calendar URLs).

| Key | Description |
| --- | --- |
| `timezone` | IANA timezone, e.g. `America/Los_Angeles` |
| `calendars` | List of `{ name, ics_url, color }` — one per calendar feed |
| `working_hours_start` / `working_hours_end` | Timeline range, `HH:MM` |
| `calendar_refresh_minutes` | How often to re-fetch ICS feeds |
| `port` | Port the Flask server listens on |
| `tasks_file` | Path to the tasks JSON file |
| `asana` | Optional, post-v1. Leave `enabled: false` |

### Getting ICS URLs

**Google Calendar**

1. Open Google Calendar on the web > Settings > select the calendar on the left.
2. Under "Integrate calendar", copy the **Secret address in iCal format**.
3. Treat this URL as a secret — anyone with it can read your calendar.

**Outlook / Microsoft 365**

1. Open Outlook on the web > Settings > Calendar > Shared calendars.
2. Under "Publish a calendar", choose the calendar and permission level, click
   **Publish**.
3. Copy the **ICS** link.

Add each as an entry under `calendars:` in `config.yaml`, with a `name` and a hex
`color` used for that calendar's events on the timeline.

## Tasks (`tasks.json`)

The right column reads from the file referenced by `tasks_file` (default
`data/tasks.json`). Each task is an object:

```json
{
  "id": "1",
  "title": "Pay invoice #4471",
  "due": "2026-06-15T17:00:00-07:00",
  "section": "Today",
  "priority": 1,
  "done": false
}
```

- `due` — ISO 8601 datetime, or `null` for no due date.
- `section` — free-text grouping header (e.g. "Today", "This Week", "Overdue").
- `priority` — `1` (highest) to `3`, or `null`.
- `done` — completed tasks are hidden from the display.

Edit this file by hand (or have another process write to it — the display reads it
read-only every 30 seconds). Tasks are sorted by `due` (soonest first, no-due-date
last), then by `priority`. Overdue tasks are highlighted.

## Running locally for development

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy config.example.yaml config.yaml   # then edit it
python app.py
```

Open `http://localhost:8080`.

## Notes

- If a calendar fetch fails, the last successful copy is served from `cache/` and a
  "stale since HH:MM" note appears under the timeline.
- All-day events appear in a band above the timeline instead of as timed blocks.
- Overlapping timed events are laid out side by side automatically.
