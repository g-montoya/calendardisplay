(function () {
  "use strict";

  const EVENTS_POLL_MS = 60 * 1000;
  const TASKS_POLL_MS = 30 * 1000;
  const NOWLINE_POLL_MS = 30 * 1000;

  let workingStartMin = 6 * 60;
  let workingEndMin = 22 * 60;
  let latestEvents = [];
  const sourceIndexMap = {};
  let sourceIndexNext = 0;

  // E-ink mode: add ?eink=1 to the URL to enable.
  const einkMode = new URLSearchParams(window.location.search).get("eink") === "1";
  if (einkMode) document.body.classList.add("eink");

  // ---------- Header: date + clock ----------

  function updateClock() {
    const now = new Date();
    document.getElementById("header-clock").textContent = now.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
    document.getElementById("header-date").textContent = now.toLocaleDateString([], {
      weekday: "long",
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  }

  // ---------- Time helpers ----------

  function parseHHMM(str) {
    const [h, m] = str.split(":").map(Number);
    return h * 60 + m;
  }

  function minutesSinceMidnight(date) {
    return date.getHours() * 60 + date.getMinutes() + date.getSeconds() / 60;
  }

  function pctFromMinutes(minutes) {
    const total = workingEndMin - workingStartMin;
    const pct = ((minutes - workingStartMin) / total) * 100;
    return Math.max(0, Math.min(100, pct));
  }

  function formatTime(date) {
    return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }

  // ---------- Timeline grid ----------

  function renderGrid() {
    const grid = document.getElementById("timeline-grid");
    grid.innerHTML = "";
    const startHour = Math.ceil(workingStartMin / 60);
    const endHour = Math.floor(workingEndMin / 60);
    for (let h = startHour; h <= endHour; h++) {
      const pct = pctFromMinutes(h * 60);

      const line = document.createElement("div");
      line.className = "hour-line";
      line.style.top = pct + "%";
      grid.appendChild(line);

      const label = document.createElement("div");
      label.className = "hour-label";
      label.style.top = pct + "%";
      const d = new Date();
      d.setHours(h, 0, 0, 0);
      label.textContent = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
      grid.appendChild(label);
    }
  }

  // ---------- Now line ----------

  function renderNowLine() {
    const nowLine = document.getElementById("now-line");
    const pct = pctFromMinutes(minutesSinceMidnight(new Date()));
    nowLine.style.top = pct + "%";
  }

  // ---------- Events ----------

  function calIndex(source) {
    if (!(source in sourceIndexMap)) {
      sourceIndexMap[source] = sourceIndexNext++ % 8;
    }
    return sourceIndexMap[source];
  }

  function layoutEvents(events) {
    const sorted = events.slice().sort((a, b) => a.startMin - b.startMin || a.endMin - b.endMin);
    const active = [];
    const placed = [];

    for (const ev of sorted) {
      for (let i = active.length - 1; i >= 0; i--) {
        if (active[i].endMin <= ev.startMin) active.splice(i, 1);
      }
      const usedCols = new Set(active.map((a) => a.col));
      let col = 0;
      while (usedCols.has(col)) col++;
      ev.col = col;
      active.push(ev);
      placed.push(ev);

      const groupMax = Math.max(...active.map((a) => a.col)) + 1;
      for (const a of active) {
        a.cols = Math.max(a.cols || 1, groupMax);
      }
    }

    return placed;
  }

  function renderEvents(events) {
    const container = document.getElementById("timeline-events");
    const alldayBand = document.getElementById("allday-band");
    container.innerHTML = "";
    alldayBand.innerHTML = "";

    const timed = [];
    for (const ev of events) {
      const start = new Date(ev.start);
      const end = new Date(ev.end);

      if (ev.all_day) {
        const chip = document.createElement("div");
        chip.className = "allday-chip";
        if (!einkMode) chip.style.background = ev.color;
        chip.textContent = ev.title;
        alldayBand.appendChild(chip);
        continue;
      }

      timed.push({
        ...ev,
        startDate: start,
        endDate: end,
        startMin: minutesSinceMidnight(start),
        endMin: minutesSinceMidnight(end),
      });
    }

    const placed = layoutEvents(timed);

    for (const ev of placed) {
      const top = pctFromMinutes(ev.startMin);
      const bottom = pctFromMinutes(ev.endMin);
      const height = Math.max(bottom - top, 1.2);
      const cols = ev.cols || 1;
      const width = 100 / cols;
      const left = ev.col * width;

      const block = document.createElement("div");
      block.className = "event-block";
      block.style.top = top + "%";
      block.style.height = height + "%";
      block.style.left = left + "%";
      block.style.width = `calc(${width}% - 0.3vw)`;
      if (!einkMode) block.style.background = ev.color;
      block.dataset.calIndex = calIndex(ev.source);

      const title = document.createElement("div");
      title.className = "event-title";
      title.textContent = ev.title;
      block.appendChild(title);

      container.appendChild(block);
    }
  }

  function renderStale(data) {
    const note = document.getElementById("stale-note");
    if (data.stale && data.stale_since) {
      note.textContent = `Stale since ${formatTime(new Date(data.stale_since))} — showing cached data`;
    } else if (data.errors && data.errors.length && latestEvents.length === 0) {
      note.textContent = "Calendar fetch error — retrying";
    } else {
      note.textContent = "";
    }
  }

  async function refreshEvents() {
    try {
      const resp = await fetch("/api/events");
      const data = await resp.json();
      workingStartMin = parseHHMM(data.working_hours_start || "06:00");
      workingEndMin = parseHHMM(data.working_hours_end || "22:00");
      latestEvents = data.events || [];
      renderGrid();
      renderEvents(latestEvents);
      renderNowLine();
      renderStale(data);
    } catch (_) {
      // Keep showing last render; retry on next poll.
    }
  }

  // ---------- Tasks ----------

  function renderTasks(data) {
    const list = document.getElementById("tasks-list");
    list.innerHTML = "";

    if (data.error) {
      const note = document.createElement("div");
      note.className = "empty-note";
      note.textContent = "Could not read tasks";
      list.appendChild(note);
      return;
    }

    if (!data.sections || data.sections.length === 0) {
      const note = document.createElement("div");
      note.className = "empty-note";
      note.textContent = "No tasks";
      list.appendChild(note);
      return;
    }

    for (const section of data.sections) {
      const title = document.createElement("div");
      title.className = "task-section-title";
      title.textContent = section.name;
      list.appendChild(title);

      for (const task of section.tasks) {
        const row = document.createElement("div");
        row.className = "task-row" + (task.overdue ? " overdue" : "");

        const titleEl = document.createElement("div");
        titleEl.className = "task-title";
        titleEl.textContent = task.title;

        const dueEl = document.createElement("div");
        dueEl.className = "task-due";
        if (task.due) {
          dueEl.textContent = formatTime(new Date(task.due));
        }

        row.appendChild(titleEl);
        row.appendChild(dueEl);
        list.appendChild(row);
      }
    }
  }

  async function refreshTasks() {
    try {
      const resp = await fetch("/api/tasks");
      const data = await resp.json();
      renderTasks(data);
    } catch (_) {
      // Keep showing last render; retry on next poll.
    }
  }

  // ---------- Midnight reload ----------
  // When the calendar day rolls over, reload the page so the timeline and
  // event data reset cleanly for the new day.

  const startDay = new Date().toDateString();

  function checkMidnight() {
    if (new Date().toDateString() !== startDay) {
      location.reload();
    }
  }

  // ---------- Init ----------

  updateClock();
  setInterval(updateClock, 1000);
  setInterval(checkMidnight, 60 * 1000);

  refreshEvents();
  setInterval(refreshEvents, EVENTS_POLL_MS);
  setInterval(renderNowLine, NOWLINE_POLL_MS);

  refreshTasks();
  setInterval(refreshTasks, TASKS_POLL_MS);
})();
