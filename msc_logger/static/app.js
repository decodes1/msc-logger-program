"use strict";

const pages = [
  ["overview", "Overview", "◫"],
  ["maintenance", "Maintenance", "☷"],
  ["diagnostics", "Troubleshooting", "⌘"],
  ["reports", "Ground reports", "↗"],
  ["inventory", "Spares inventory", "▤"],
  ["history", "Activity log", "◷"],
  ["simulation", "Demo & data", "⚙"],
];
let state = null;
let current = "overview";
let pollingDelay = 2000;
let stopped = false;
let toastTimer;
let modalContext = null;
const pendingRequests = new Map();
const main = document.querySelector("#main");
const modal = document.querySelector("#modal");
const hash = new URLSearchParams(location.hash.slice(1));
let token = hash.get("token") || "";
try {
  if (token) sessionStorage.setItem("msc-session", token);
  else token = sessionStorage.getItem("msc-session") || "";
} catch (_) {
  // The launch token still works when browser session storage is unavailable.
}
if (hash.has("token")) history.replaceState(null, "", location.pathname);

const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[character]);
const stamp = (value) => new Date(value * 1000).toLocaleString();
const pill = (label, tone = "") => `<span class="pill ${tone}">${escapeHtml(label)}</span>`;
const head = (title, description, extra = "") => `<div class="page-head"><div><h1>${title}</h1><p class="subtle">${description}</p></div>${extra}</div>`;
const empty = (message) => `<div class="empty">${message}</div>`;

function toast(message, error = false) {
  const element = document.querySelector("#toast");
  clearTimeout(toastTimer);
  element.textContent = message;
  element.className = `toast${error ? " error" : ""}`;
  element.hidden = false;
  toastTimer = setTimeout(() => { element.hidden = true; }, error ? 10000 : 5000);
}

async function request(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch(path, {
      ...options,
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", ...options.headers },
      signal: controller.signal,
    });
    if (!response.ok) {
      const data = await response.json();
      const error = new Error(data.error || "The request could not be completed.");
      error.status = response.status;
      throw error;
    }
    return response;
  } catch (error) {
    if (!error.status) {
      throw new Error("The local app is not responding. Your form is still here. Reopen MSC Logger if needed, then retry.");
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

async function action(name, data, message = true) {
  const key = name + JSON.stringify(data);
  const operationId = pendingRequests.get(key) || crypto.randomUUID();
  pendingRequests.set(key, operationId);
  try {
    const response = await request(`/api/action/${name}`, {
      method: "POST",
      body: JSON.stringify({ ...data, operation_id: operationId }),
    });
    const result = await response.json();
    pendingRequests.delete(key);
    await refresh(false);
    if (message) toast(result.message);
    return result;
  } catch (error) {
    if (error.status && error.status < 500) pendingRequests.delete(key);
    throw error;
  }
}

function navigation() {
  document.querySelector("#navigation").innerHTML = pages.map(([id, label, symbol]) =>
    `<a href="#${id}" ${id === current ? 'aria-current="page"' : ""}><span class="nav-symbol" aria-hidden="true">${symbol}</span>${label}</a>`
  ).join("");
}

function chrome() {
  document.querySelector("#day-label").textContent = `MISSION DAY ${String(state.settings.day).padStart(3, "0")}`;
  document.querySelector("#workspace-label").textContent = state.demo ? "Rehearsal workspace · separate demo records" : "Mars transit habitat · saved training workspace";
  const banner = document.querySelector("#connection-banner");
  banner.hidden = !state.health.error;
  banner.textContent = state.health.error;
}

function due(task) {
  if (task.last_day === state.settings.day) return pill("Completed today", "good");
  if (task.due_in < 0) return pill(`${Math.abs(task.due_in)}d overdue`, "bad");
  if (task.due_in === 0) return pill("Due today", "warn");
  return pill(`Due in ${task.due_in}d`, task.due_in === 1 ? "warn" : "");
}

function taskRows(tasks, compact = false) {
  return tasks.map((task) => `<div class="task-row">
    <span class="task-marker" aria-hidden="true">${task.last_day === state.settings.day ? "✓" : "□"}</span>
    <div class="task-text"><h3>${escapeHtml(task.name)}</h3><p>${escapeHtml(task.location)}${compact ? "" : ` · Every ${task.interval} days`}</p></div>
    ${due(task)}<button class="text-button" data-task="${task.id}">Review<span class="sr-only"></span> ↗</button>
  </div>`).join("") || empty("No tasks match this filter.");
}

function sparkline(sensor) {
  const history = sensor.history;
  if (history.length < 2) return '<p class="subtle">Collecting a trend…</p>';
  const min = Math.min(sensor.low - 5, ...history.map((sample) => sample.value));
  const max = Math.max(sensor.high + 5, ...history.map((sample) => sample.value));
  const points = history.map((sample, index) => `${(index / (history.length - 1) * 400).toFixed(1)},${(40 - (sample.value - min) / (max - min) * 35).toFixed(1)}`).join(" ");
  return `<svg class="sparkline ${sensor.quality === "warning" ? "warning" : ""}" viewBox="0 0 400 45" preserveAspectRatio="none" role="img" aria-label="Recent ${escapeHtml(sensor.name)} trend"><polyline points="${points}"></polyline></svg>`;
}

function sensorCards() {
  return state.sensors.map((sensor) => `<div class="sensor">
    <div class="sensor-head"><h3>${sensor.name}</h3>${pill(sensor.quality, sensor.quality === "nominal" ? "good" : "warn")}</div>
    <div class="sensor-number">${sensor.latest ? sensor.latest.value.toFixed(1) : "—"} <small>${sensor.unit}</small></div>
    ${sparkline(sensor)}<div class="subtle">${sensor.latest ? `${Math.round(sensor.age)}s old · ${escapeHtml(sensor.latest.source)}` : "No valid sample received"} · illustrative thresholds</div>
  </div>`).join("");
}

function overview() {
  const dueCount = state.tasks.filter((task) => task.due_in <= 0 && task.last_day !== state.settings.day).length;
  const queued = Object.entries(state.report_counts).filter(([key]) => key !== "delivered").reduce((sum, [, count]) => sum + count, 0);
  const attention = state.sensors.filter((sensor) => sensor.quality !== "nominal").length;
  const low = state.inventory.filter((item) => item.quantity <= item.minimum).length;
  return head("Mission overview", "Your crew workspace, wherever the mission takes you.", pill("SIMULATION", "")) + `
    <section class="hero"><div><span class="eyebrow">LONG-DURATION TRANSIT / HABITAT MAINTENANCE</span>
      <h2>Keep the habitat moving.</h2><p>Review today’s maintenance, follow equipment observations, and keep a record for ground. Your work stays on this computer, even when the simulated link is down.</p>
      <button class="primary" data-nav="maintenance">Open maintenance queue ↗</button></div>
      <img class="hero-graphic" src="/assets/icon.png" alt="MSC orbital emblem">
    </section>
    <div class="metrics">
      <div class="metric"><div class="metric-label">Tasks needing attention</div><div class="metric-value">${dueCount.toString().padStart(2, "0")}</div><div class="metric-foot">Due today or overdue</div></div>
      <div class="metric"><div class="metric-label">Reports awaiting receipt</div><div class="metric-value">${queued.toString().padStart(2, "0")}</div><div class="metric-foot">Saved in the local outbox</div></div>
      <div class="metric"><div class="metric-label">Telemetry flags</div><div class="metric-value">${attention.toString().padStart(2, "0")}</div><div class="metric-foot">Warning, stale, or missing</div></div>
      <div class="metric"><div class="metric-label">Spares to replenish</div><div class="metric-value">${low.toString().padStart(2, "0")}</div><div class="metric-foot">At or below reserve level</div></div>
    </div>
    <div class="grid-two"><div>
      <section class="card"><div class="card-heading"><h2>Maintenance queue</h2><button class="text-button" data-nav="maintenance">View all ↗</button></div>${taskRows(state.tasks, true)}</section>
      <section class="card"><div class="card-heading"><h2>Ground connection</h2>${pill(state.settings.online ? "Link available" : "Link unavailable", state.settings.online ? "good" : "warn")}</div>
        <p class="subtle">${state.settings.delay}s one-way simulated delay. A report becomes delivered only after its round-trip acknowledgement.</p>
        <div class="actions"><button data-link>${state.settings.online ? "Simulate link loss" : "Restore simulated link"}</button><button class="text-button" data-nav="reports">Open outbox ↗</button></div>
      </section></div>
      <section class="card"><div class="card-heading"><h2>Habitat telemetry</h2>${pill("SIMULATED")}</div>${sensorCards()}</section>
    </div>`;
}

function maintenance() {
  return head("Maintenance", "A clear checklist. A saved record. A recalculated due date.") + `
    <div class="notice">Training checklists only. Actual spacecraft work requires mission-approved procedures.</div>
    <div class="toolbar"><input id="task-search" aria-label="Search maintenance" placeholder="Search tasks or locations…"><select id="task-filter" aria-label="Filter maintenance"><option value="all">All tasks</option><option value="due">Due or overdue</option><option value="done">Completed today</option></select></div>
    <section class="card" id="task-list">${taskRows(state.tasks)}</section>
    <section class="card"><h2>Recent completions</h2>${state.completions.map((item) => `<div class="list-row"><div><h3>${escapeHtml(state.tasks.find((task) => task.id === item.task_id)?.name)}</h3><p class="subtle">Day ${item.day} · ${escapeHtml(item.operator)} · ${escapeHtml(item.note || "No additional notes")}</p></div>${pill("Recorded", "good")}</div>`).join("") || empty("Your first completed checklist will appear here.")}</section>`;
}

function diagnostics() {
  return head("Troubleshooting", "Capture an observation and preserve the path to a resolution.") + `
    <div class="info-strip">Guided observation only. Urgent findings always lead to an escalation record.</div>
    <div class="inventory-grid">${Object.entries(state.trees).map(([id, tree]) => `<section class="card"><span class="eyebrow">GUIDED OBSERVATION</span><h2>${tree.title}</h2><p class="subtle">${tree.question}</p><button data-tree="${id}">Start observation ↗</button></section>`).join("")}</div>
    <section class="card"><h2>Recent cases</h2>${state.cases.map((item) => `<div class="list-row"><div><h3>${escapeHtml(state.trees[item.tree].title)}</h3><p class="subtle">${escapeHtml(item.note)} · ${stamp(item.created)}</p></div>${pill(item.outcome, item.outcome === "resolved" ? "good" : "warn")}</div>`).join("") || empty("Saved observations will appear here.")}</section>`;
}

function reportList() {
  const status = { queued: ["Queued locally", "warn"], in_flight: ["Awaiting receipt", ""], retry: ["Retry scheduled", "warn"], delivered: ["Simulated receipt", "good"] };
  return state.reports.map((report) => {
    const [label, tone] = status[report.status];
    const context = JSON.parse(report.context);
    return `<article class="report-item"><div class="row">${pill(label, tone)}${report.priority === "urgent" ? pill("Urgent", "bad") : ""}<strong>${escapeHtml(report.category)}</strong></div>
      <p>${escapeHtml(report.description)}</p>${context.observation ? `<p class="subtle">Observation path: ${escapeHtml(context.observation)}</p>` : ""}
      <div class="report-meta">${report.id.slice(0, 8)} · ${stamp(report.created)} · ${report.attempts} transmission attempts</div>
      ${report.receipt ? `<div class="report-meta">Receipt: ${escapeHtml(report.receipt)}</div>` : ""}
      ${report.status === "in_flight" ? `<div class="report-meta">${state.settings.online ? `Receipt due in about ${Math.max(0, Math.ceil(report.ack_at - state.now))}s` : "Waiting for link restoration"}</div>` : ""}
      ${report.status === "retry" ? `<button class="text-button" data-retry="${report.id}">Retry now</button>` : ""}</article>`;
  }).join("") || empty("No reports yet. Your first report will stay here until acknowledged.");
}

function reports() {
  return head("Ground reports", "A persistent outbox for an intermittent connection.", '<button data-export="reports">Export reports</button>') + `
    <div class="grid-two"><section class="card"><h2>New report</h2><p class="subtle">Saved locally first. Delivery refers to the built-in ground simulator.</p>
      <form id="report-form"><div class="two-fields"><div><label for="category">Category</label><select id="category" name="category"><option>Equipment</option><option>Environmental</option><option>Maintenance</option><option>Other</option></select></div>
      <div><label for="priority">Priority</label><select id="priority" name="priority"><option value="routine">Routine</option><option value="urgent">Urgent</option></select></div></div>
      <label for="description">What happened?</label><textarea id="description" name="description" maxlength="2000" required placeholder="Include the equipment, location, time, and what you observed."></textarea>
      <p class="subtle">A queued report does not replace an emergency procedure.</p><div class="actions"><button class="primary">Save to outbox</button></div></form>
    </section><section class="card"><div class="card-heading"><h2>Outbox & receipts</h2><button class="text-button" data-link>${state.settings.online ? "Drop link" : "Restore link"}</button></div><p class="subtle">Latest 100 reports. Export includes all saved reports.</p><div id="report-list">${reportList()}</div></section></div>`;
}

function inventoryCards(query = "") {
  const items = state.inventory.filter((item) => `${item.name} ${item.location}`.toLowerCase().includes(query.toLowerCase()));
  return items.map((item) => `<section class="card"><div class="card-heading"><h2>${item.name}</h2>${item.quantity <= item.minimum ? pill("Low stock", "warn") : pill("Available", "good")}</div>
    <p class="subtle">${item.location}</p><div class="stock-quantity">${item.quantity} <small>${item.unit}</small></div><p class="subtle">Reserve threshold: ${item.minimum}</p><button data-stock="${item.id}">Use or replenish</button></section>`).join("") || empty("No spares match your search.");
}

function inventory() {
  return head("Spares inventory", "Find what you need and leave a traceable stock adjustment.") + `
    <div class="toolbar"><input id="stock-search" aria-label="Search spares" placeholder="Search spares or storage locations…"></div><div id="inventory-list" class="inventory-grid">${inventoryCards()}</div>`;
}

function historyView() {
  return head("Activity log", "Recent events across maintenance, telemetry, and communication.", '<button data-export="history">Export activity</button>') + `
    <section class="card"><p class="subtle">Showing the latest 100 events. The local journal retains 10,000 events.</p><div class="timeline">${state.events.map((item) => `<article class="event"><time>${stamp(item.created)}</time><p>${escapeHtml(item.message)}</p>${pill(item.kind, item.level === "warning" ? "warn" : "")}</article>`).join("")}</div></section>`;
}

function simulation() {
  const settings = state.settings;
  return head("Demo & data", "Rehearse failures, inspect evidence, and protect your local records.") + `
    <div class="notice">All signal values and communication events are synthetic. A 4-second one-way delay accelerates the demo; 20 minutes illustrates a long transit communication delay.</div>
    <div class="grid-two"><section class="card"><h2>Simulation controls</h2>
      <form id="simulation-form"><label for="fault">Telemetry scenario</label><select id="fault" name="fault">${[["normal", "Normal readings"], ["low_airflow", "Low airflow warning"], ["corrupt", "Corrupted airflow sample"], ["missing", "Missing airflow samples"], ["delayed", "Airflow delayed by 90 seconds"]].map(([value, label]) => `<option value="${value}" ${settings.fault === value ? "selected" : ""}>${label}</option>`).join("")}</select>
      <label for="delay">One-way communication delay</label><select id="delay" name="delay">${[[4, "4 seconds · presentation mode"], [60, "1 minute · short test"], [1200, "20 minutes · transit illustration"]].map(([value, label]) => `<option value="${value}" ${settings.delay === value ? "selected" : ""}>${label}</option>`).join("")}</select>
      <label class="check-row"><input type="checkbox" name="feed" ${settings.feed ? "checked" : ""}>Generate telemetry every two seconds</label>
      <label class="check-row"><input type="checkbox" name="online" ${settings.online ? "checked" : ""}>Ground link available</label>
      <label class="check-row"><input type="checkbox" name="drop_ack" ${settings.drop_ack ? "checked" : ""}>Drop the next acknowledgement once</label>
      <div class="actions"><button class="primary">Apply simulation settings</button><button type="button" data-advance>Advance mission day</button></div></form>
    </section><div><section class="card"><h2>Local records & backup</h2><p class="subtle">Data folder: <code>${escapeHtml(state.data_path)}</code></p>
      <p class="subtle">Verified backups every five minutes and at clean exit. Keep a downloaded backup on a separate drive for protection against disk failure.</p><p class="subtle">Last scheduled backup: ${state.health.backup_at ? stamp(state.health.backup_at) : "Pending"}</p>
      <div class="actions"><button data-backup>Download database backup</button><button data-export="telemetry">Export telemetry</button><button data-export="completions">Export completions</button><button data-export="cases">Export cases</button></div></section>
      <section class="card"><h2>Rehearsal workspace</h2><p class="subtle">${state.demo ? "You are in the separate demo workspace. Reset only clears these rehearsal records." : "You are in the saved workspace. Launch Demo.cmd in the Windows package to rehearse with separate records."}</p>
      ${state.demo ? '<button class="danger" data-reset>Reset rehearsal records</button>' : ""}</section></div></div>
    <section class="card"><h2>Import telemetry CSV</h2><p class="subtle">At most 1,000 rows and 200 KB. Use Unix timestamps in seconds. An invalid row rejects the entire import. Duplicate sensor/timestamp pairs are skipped. Pause the generated feed to inspect imported readings.</p>
      <pre>sensor,value,observed_at\nairflow,92,${Math.floor(state.now)}\nhumidity,44,${Math.floor(state.now)}</pre>
      <form id="import-form"><label for="csv-file">Choose a CSV file</label><input type="file" id="csv-file" accept=".csv,text/csv" required><div class="actions"><button>Validate and import</button></div></form>
      <p class="subtle">The app retains the newest 1,000 readings per sensor. Exports contain retained readings. Data stays on this computer and is not encrypted by MSC Logger.</p>
    </section>`;
}

const views = { overview, maintenance, diagnostics, reports, inventory, history: historyView, simulation };
function render() {
  if (!state) return;
  navigation();
  chrome();
  main.innerHTML = views[current]();
}

async function refresh(live = true) {
  const response = await request("/api/state");
  state = await response.json();
  chrome();
  if (!live) return;
  if (current === "overview" && !modal.open && !main.contains(document.activeElement)) main.innerHTML = overview();
  if (current === "reports") {
    const list = document.querySelector("#report-list");
    if (list && !list.contains(document.activeElement)) list.innerHTML = reportList();
    const button = main.querySelector("[data-link]");
    if (button) button.textContent = state.settings.online ? "Drop link" : "Restore link";
  }
}

async function poll() {
  if (stopped) return;
  try {
    await refresh(true);
    pollingDelay = 2000;
    if (!main.querySelector(".page-head")) render();
  } catch (error) {
    const banner = document.querySelector("#connection-banner");
    banner.textContent = error.message;
    banner.hidden = false;
    pollingDelay = Math.min(pollingDelay * 2, 15000);
  }
  if (!stopped) setTimeout(poll, pollingDelay);
}

function showModal(title, body, context) {
  modalContext = context;
  modal.innerHTML = `<div class="modal-head"><h2 id="modal-title">${title}</h2><button aria-label="Close dialog" data-close>×</button></div>${body}<p class="modal-error" role="alert"></p>`;
  modal.showModal();
}

function openTask(id) {
  const task = state.tasks.find((item) => item.id === id);
  const complete = task.last_day === state.settings.day;
  showModal(task.name, `<p class="subtle">${task.location} · Every ${task.interval} days</p><div class="notice">Illustrative training checklist. Save each observation before recording completion.</div>
    <form id="task-form">${task.steps.map((step, index) => `<label class="check-row"><input type="checkbox" name="step-${index}" ${task.checks[index] || complete ? "checked" : ""} ${complete ? "disabled" : ""}>${index + 1}. ${step}</label>`).join("")}
      ${complete ? '<p class="subtle">This task is already recorded for today.</p>' : '<label for="operator">Crew member</label><input id="operator" name="operator" maxlength="80" required placeholder="Name or crew identifier"><label for="task-note">Completion note</label><textarea id="task-note" name="note" maxlength="2000" placeholder="Record findings or exceptions."></textarea><div class="actions"><button type="button" data-save-progress>Save progress</button><button class="primary">Record completion</button></div>'}
    </form>`, { type: "task", task: structuredClone(task), day: state.settings.day });
}

function openTree(id) {
  const tree = state.trees[id];
  showModal(tree.title, `<p>${tree.question}</p><div class="actions">${tree.options.map((option, index) => `<button data-choice="${index}">${option.label}</button>`).join("")}</div>`, { type: "case", tree: id });
}

function chooseObservation(choice) {
  const treeId = modalContext.tree;
  const tree = state.trees[treeId];
  const option = tree.options[choice];
  showModal(tree.title, `${pill(option.label, option.urgent ? "bad" : "")}<ol>${option.steps.map((step) => `<li>${step}</li>`).join("")}</ol>
    <form id="case-form"><label for="case-note">Observation notes</label><textarea id="case-note" name="note" required maxlength="2000"></textarea>
      <div class="actions">${option.urgent ? "" : '<button name="outcome" value="resolved">Record resolved</button>'}<button name="outcome" value="escalated" class="primary">Save & queue report</button></div></form>`, { type: "case", tree: treeId, choice });
}

function openStock(id) {
  const item = state.inventory.find((value) => value.id === id);
  showModal(item.name, `<p class="subtle">${item.location} · Current stock: ${item.quantity}</p><form id="stock-form">
    <label for="direction">Adjustment</label><select id="direction" name="direction"><option value="-1">Use stock</option><option value="1">Replenish stock</option></select>
    <label for="quantity">Quantity</label><input id="quantity" name="quantity" type="number" min="1" max="10000" step="1" required>
    <label for="reason">Reason / crew member</label><input id="reason" name="reason" maxlength="300" required><div class="actions"><button class="primary">Save adjustment</button></div></form>`, { type: "stock", item: structuredClone(item) });
}

async function download(path, name) {
  const response = await request(path);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function taskPayload() {
  return { id: modalContext.task.id, last_day: modalContext.task.last_day, day: modalContext.day };
}

async function saveProgress() {
  const checks = modalContext.task.steps.map((_, index) => modal.querySelector(`[name="step-${index}"]`).checked);
  return action("task_progress", { ...taskPayload(), checks }, false);
}

async function handleClick(event) {
  const button = event.target.closest("button");
  if (!button || button.disabled) return;
  const data = button.dataset;
  if (data.nav) { location.hash = data.nav; return; }
  if (data.task) { openTask(data.task); return; }
  if (data.tree) { openTree(data.tree); return; }
  if (data.stock) { openStock(data.stock); return; }
  if ("choice" in data) { chooseObservation(Number(data.choice)); return; }
  if ("close" in data) { modal.close(); return; }
  if ("reset" in data) {
    showModal("Reset rehearsal records?", '<p>This clears only the demo workspace, including its tasks, reports, and history.</p><form id="reset-form"><label for="confirmation">Type RESET DEMO</label><input id="confirmation" name="confirmation" required autocomplete="off"><div class="actions"><button class="danger">Reset demo</button></div></form>', { type: "reset" });
    return;
  }
  if (button.id === "quit") {
    showModal("Close MSC Logger?", '<p>Your saved records remain on this computer. Unsaved form text will not be saved.</p><button class="primary" data-confirm-quit>Save records & exit</button>', { type: "quit" });
    return;
  }
  if (button.type === "submit" && button.closest("form")) return;
  button.disabled = true;
  try {
    if ("link" in data) {
      await action("settings", { online: !state.settings.online });
      if (current === "overview") render();
    } else if ("advance" in data) {
      await action("settings", { advance_day: true });
      render();
    } else if ("saveProgress" in data) {
      await saveProgress();
      toast("Checklist progress saved locally.");
    } else if (data.retry) {
      await action("retry", { id: data.retry });
    } else if (data.export) {
      await download(`/api/export?kind=${data.export}`, `msc-${data.export}.csv`);
    } else if ("backup" in data) {
      await download("/api/backup", "msc-backup.sqlite3");
    } else if ("confirmQuit" in data) {
      await request("/api/shutdown", { method: "POST", body: JSON.stringify({ confirm: true }) });
      stopped = true;
      modal.close();
      main.innerHTML = head("Workspace closed", "Your saved records are safe on this computer. The desktop window will close shortly.");
      document.querySelector("#quit").disabled = true;
    }
  } catch (error) {
    if (modal.open) modal.querySelector(".modal-error").textContent = error.message;
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function handleSubmit(event) {
  event.preventDefault();
  const form = event.target;
  const values = Object.fromEntries(new FormData(form));
  const buttons = [...form.querySelectorAll("button")];
  const submitter = event.submitter;
  buttons.forEach((button) => { button.disabled = true; });
  try {
    if (form.id === "report-form") {
      await action("report", values);
      form.reset();
      document.querySelector("#report-list").innerHTML = reportList();
    } else if (form.id === "task-form") {
      await saveProgress();
      await action("task_complete", { ...taskPayload(), operator: values.operator, note: values.note });
      modal.close();
      render();
    } else if (form.id === "stock-form") {
      await action("inventory", { id: modalContext.item.id, revision: modalContext.item.revision, delta: Number(values.quantity) * Number(values.direction), reason: values.reason });
      modal.close();
      render();
    } else if (form.id === "case-form") {
      await action("case", { tree: modalContext.tree, choice: modalContext.choice, outcome: submitter.value, note: values.note });
      modal.close();
      render();
    } else if (form.id === "simulation-form") {
      await action("settings", { fault: values.fault, delay: Number(values.delay), online: "online" in values, feed: "feed" in values, drop_ack: "drop_ack" in values });
      render();
    } else if (form.id === "import-form") {
      const file = document.querySelector("#csv-file").files[0];
      if (file.size > 200000) throw new Error("Choose a CSV file no larger than 200 KB.");
      await action("import", { csv: await file.text() });
      form.reset();
    } else if (form.id === "reset-form") {
      await action("demo_reset", { confirmation: values.confirmation });
      modal.close();
      render();
    }
  } catch (error) {
    if (modal.open) modal.querySelector(".modal-error").textContent = error.message;
    toast(error.message, true);
  } finally {
    buttons.forEach((button) => { button.disabled = false; });
  }
}

document.addEventListener("click", handleClick);
document.addEventListener("submit", handleSubmit);
document.addEventListener("input", (event) => {
  if (event.target.id === "stock-search") document.querySelector("#inventory-list").innerHTML = inventoryCards(event.target.value);
  if (["task-search", "task-filter"].includes(event.target.id)) {
    const query = document.querySelector("#task-search").value.toLowerCase();
    const filter = document.querySelector("#task-filter").value;
    const tasks = state.tasks.filter((task) => `${task.name} ${task.location}`.toLowerCase().includes(query) &&
      (filter === "all" || (filter === "due" ? task.due_in <= 0 && task.last_day !== state.settings.day : task.last_day === state.settings.day)));
    document.querySelector("#task-list").innerHTML = taskRows(tasks);
  }
});
window.addEventListener("hashchange", () => {
  const next = location.hash.slice(1);
  if (views[next]) {
    current = next;
    render();
  }
});
if (views[location.hash.slice(1)]) current = location.hash.slice(1);
navigation();
poll();
