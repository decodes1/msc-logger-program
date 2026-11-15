"""Maintenance rules, telemetry validation, and a persistent simulated outbox."""

import csv
import hashlib
import io
import json
import math
import time
import uuid

from .catalog import SENSORS, SPARES, TASKS, TREES
from .storage import set_setting, setting


class ValidationError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def text_field(value, name, limit=2000, required=True):
    if not isinstance(value, str) or len(value) > limit:
        raise ValidationError(f"{name} must be text with at most {limit} characters.")
    value = value.strip()
    if required and not value:
        raise ValidationError(f"Enter {name.lower()}.")
    return value


def integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValidationError(f"{name} must be a whole number from {minimum} to {maximum}.")
    return value


class Engine:
    def __init__(self, store, clock=time.time, demo=False):
        self.store = store
        self.clock = clock
        self.demo = demo
        self.last_sample = 0
        with store.transaction() as db:
            if not db.execute("SELECT 1 FROM settings LIMIT 1").fetchone():
                self.seed(db)

    def seed(self, db):
        for key, value in {"day": 1, "online": False, "delay": 4,
                           "feed": True, "fault": "normal", "drop_ack": False}.items():
            set_setting(db, key, value)
        for task in TASKS:
            db.execute("INSERT INTO tasks(id, last_day) VALUES (?, ?)",
                       (task["id"], task["last_day"]))
        for item in SPARES:
            db.execute("INSERT INTO inventory(id, quantity) VALUES (?, ?)", (item[0], item[3]))
        self.event(db, "info", "startup", "Training workspace initialized. All telemetry is simulated.")

    def event(self, db, level, kind, message):
        db.execute("INSERT INTO events(created, level, kind, message) VALUES (?, ?, ?, ?)",
                   (self.clock(), level, kind, message))
        db.execute("DELETE FROM events WHERE id <= (SELECT MAX(id)-10000 FROM events)")

    def command(self, action, data):
        if not isinstance(data, dict):
            raise ValidationError("The request must be a JSON object.")
        operation = text_field(data.get("operation_id"), "Operation ID", 80)
        fingerprint = hashlib.sha256(json.dumps([action, data], sort_keys=True).encode()).hexdigest()
        handlers = {
            "task_progress": self.task_progress, "task_complete": self.task_complete,
            "inventory": self.inventory, "report": self.report, "case": self.case,
            "settings": self.settings, "retry": self.retry, "import": self.import_csv,
            "demo_reset": self.demo_reset,
        }
        if action not in handlers:
            raise ValidationError("Unknown action.", 404)
        with self.store.transaction() as db:
            previous = db.execute("SELECT * FROM operations WHERE id=?", (operation,)).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise ValidationError("This request ID was already used for different data.", 409)
                return json.loads(previous["result"])
            result = handlers[action](db, data) or {"message": "Saved locally."}
            db.execute("INSERT INTO operations VALUES (?, ?, ?, ?)",
                       (operation, fingerprint, json.dumps(result), self.clock()))
            # Requests remain replay-safe for seven days; domain constraints also prevent double completion.
            db.execute("DELETE FROM operations WHERE created < ?", (self.clock() - 7 * 86400,))
            return result

    def task_record(self, db, data):
        task = next((t for t in TASKS if t["id"] == data.get("id")), None)
        if task is None:
            raise ValidationError("Task not found.", 404)
        row = db.execute("SELECT * FROM tasks WHERE id=?", (task["id"],)).fetchone()
        if data.get("last_day") != row["last_day"] or data.get("day") != setting(db, "day"):
            raise ValidationError("This task changed. Refresh and review its current state.", 409)
        return task, row

    def task_progress(self, db, data):
        task, row = self.task_record(db, data)
        checks = data.get("checks")
        if not isinstance(checks, list) or len(checks) != len(task["steps"]) or any(type(x) is not bool for x in checks):
            raise ValidationError("Checklist must contain one true/false value per step.")
        if row["last_day"] == setting(db, "day"):
            raise ValidationError("This task is already completed today.", 409)
        db.execute("UPDATE tasks SET checks=? WHERE id=?", (json.dumps(checks), task["id"]))

    def task_complete(self, db, data):
        task, row = self.task_record(db, data)
        day = setting(db, "day")
        if row["last_day"] == day:
            raise ValidationError("This task is already completed today.", 409)
        checks = json.loads(row["checks"])
        if len(checks) != len(task["steps"]) or not all(checks):
            raise ValidationError("Complete and save every checklist step first.")
        operator = text_field(data.get("operator"), "Crew member", 80)
        note = text_field(data.get("note", ""), "Note", required=False)
        db.execute("INSERT INTO completions(task_id, day, operator, note, created) VALUES (?, ?, ?, ?, ?)",
                   (task["id"], day, operator, note, self.clock()))
        db.execute("UPDATE tasks SET last_day=?, checks='[]' WHERE id=?", (day, task["id"]))
        self.event(db, "info", "maintenance", f"{task['name']} completed by {operator} on day {day}.")
        return {"message": "Completion saved. The next due date has been recalculated."}

    def inventory(self, db, data):
        delta = integer(data.get("delta"), "Quantity change", -10000, 10000)
        if delta == 0:
            raise ValidationError("Enter a non-zero quantity change.")
        reason = text_field(data.get("reason"), "Reason", 300)
        row = db.execute("SELECT * FROM inventory WHERE id=?", (data.get("id"),)).fetchone()
        if not row:
            raise ValidationError("Spare not found.", 404)
        if data.get("revision") != row["revision"]:
            raise ValidationError("Stock changed in another window. Refresh before trying again.", 409)
        quantity = row["quantity"] + delta
        if not 0 <= quantity <= 100000:
            raise ValidationError("Stock must stay between 0 and 100,000.")
        db.execute("UPDATE inventory SET quantity=?, revision=revision+1 WHERE id=?", (quantity, row["id"]))
        self.event(db, "info", "inventory", f"{row['id']}: {delta:+d}, balance {quantity}. {reason}")

    def add_report(self, db, category, description, priority, context):
        count = db.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        if count >= 5000:
            raise ValidationError("Report capacity reached. Export records and start another workspace.", 409)
        report_id = str(uuid.uuid4())
        db.execute("""INSERT INTO reports
                   (id, category, description, priority, created, status, context)
                   VALUES (?, ?, ?, ?, ?, 'queued', ?)""",
                   (report_id, category, description, priority, self.clock(), json.dumps(context)))
        self.event(db, "info", "report", f"Report {report_id[:8]} queued locally ({priority}).")
        return report_id

    def report(self, db, data):
        category = text_field(data.get("category"), "Category", 80)
        if category not in ("Equipment", "Environmental", "Maintenance", "Other"):
            raise ValidationError("Choose a valid report category.")
        description = text_field(data.get("description"), "Description")
        priority = data.get("priority")
        if priority not in ("routine", "urgent"):
            raise ValidationError("Choose a valid priority.")
        report_id = self.add_report(db, category, description, priority, {"day": setting(db, "day")})
        return {"message": "Report saved to the persistent outbox.", "id": report_id}

    def case(self, db, data):
        tree = TREES.get(data.get("tree"))
        if not tree:
            raise ValidationError("Choose a valid troubleshooting category.")
        choice = integer(data.get("choice"), "Observation", 0, len(tree["options"]) - 1)
        option = tree["options"][choice]
        outcome = data.get("outcome")
        if outcome not in ("resolved", "escalated") or (option["urgent"] and outcome != "escalated"):
            raise ValidationError("This observation must be escalated.")
        note = text_field(data.get("note"), "Observation notes")
        case_id = str(uuid.uuid4())
        db.execute("INSERT INTO cases VALUES (?, ?, ?, ?, ?, ?)",
                   (case_id, data["tree"], choice, outcome, note, self.clock()))
        report_id = None
        if outcome == "escalated":
            report_id = self.add_report(db, tree["title"], note,
                                        "urgent" if option["urgent"] else "routine",
                                        {"case_id": case_id, "observation": option["label"],
                                         "steps": option["steps"], "day": setting(db, "day")})
        self.event(db, "info", "troubleshooting", f"{tree['title']}: {option['label']} - {outcome}.")
        return {"message": "Case saved." + (" Report queued with the troubleshooting path." if report_id else ""),
                "id": case_id, "report_id": report_id}

    def settings(self, db, data):
        allowed = {"online", "delay", "feed", "fault", "drop_ack", "advance_day"}
        changes = {k: v for k, v in data.items() if k != "operation_id"}
        if not changes or set(changes) - allowed:
            raise ValidationError("Unknown simulation setting.")
        for key, value in changes.items():
            if key in ("online", "feed", "drop_ack") and type(value) is not bool:
                raise ValidationError(f"{key} must be true or false.")
            if key == "delay" and (type(value) is not int or value not in (4, 60, 1200)):
                raise ValidationError("Choose 4, 60, or 1200 seconds of one-way delay.")
            if key == "fault" and value not in ("normal", "low_airflow", "corrupt", "missing", "delayed"):
                raise ValidationError("Unknown telemetry fault.")
            if key == "advance_day":
                if value is not True:
                    raise ValidationError("Advance day must be true.")
                if setting(db, "day") >= 100000:
                    raise ValidationError("Maximum mission day reached.")
                set_setting(db, "day", setting(db, "day") + 1)
                db.execute("UPDATE tasks SET checks='[]'")
            else:
                set_setting(db, key, value)
        self.event(db, "info", "simulation", "Simulation settings: " + json.dumps(changes))

    def retry(self, db, data):
        row = db.execute("SELECT * FROM reports WHERE id=?", (data.get("id"),)).fetchone()
        if not row:
            raise ValidationError("Report not found.", 404)
        if row["status"] != "retry":
            raise ValidationError("Only a report waiting to retry can be retried.", 409)
        db.execute("UPDATE reports SET next_at=0 WHERE id=?", (row["id"],))

    def validate_sample(self, sensor, value, observed):
        if sensor not in SENSORS:
            raise ValidationError("Unknown sensor. Use airflow, humidity, or temperature.")
        if isinstance(value, bool) or isinstance(observed, bool):
            raise ValidationError("Telemetry values and timestamps must be numeric.")
        try:
            value, observed = float(value), float(observed)
        except (TypeError, ValueError):
            raise ValidationError("Telemetry values and timestamps must be numeric.") from None
        limits = SENSORS[sensor]
        if not math.isfinite(value) or not limits["min"] <= value <= limits["max"]:
            raise ValidationError(f"{sensor}: value outside the accepted training range.")
        if not math.isfinite(observed) or not 0 < observed <= self.clock() + 30:
            raise ValidationError("Sample timestamp must be positive and no more than 30 seconds ahead.")
        return sensor, value, observed

    def insert_sample(self, db, sample, source):
        cursor = db.execute("INSERT OR IGNORE INTO samples(sensor, value, observed, received, source) VALUES (?, ?, ?, ?, ?)",
                            (*sample, self.clock(), source))
        return cursor.rowcount

    def trim_samples(self, db):
        for sensor in SENSORS:
            db.execute("""DELETE FROM samples WHERE sensor=? AND id NOT IN
                       (SELECT id FROM samples WHERE sensor=? ORDER BY observed DESC LIMIT 1000)""", (sensor, sensor))

    def import_csv(self, db, data):
        content = text_field(data.get("csv"), "CSV data", 200000)
        try:
            reader = csv.DictReader(io.StringIO(content), strict=True)
            if reader.fieldnames != ["sensor", "value", "observed_at"]:
                raise ValidationError("CSV headers must be exactly: sensor,value,observed_at")
            rows = []
            for line, row in enumerate(reader, 2):
                if line > 1001:
                    raise ValidationError("Import at most 1,000 samples at a time.")
                if None in row or any(v is None for v in row.values()):
                    raise ValidationError(f"Line {line}: expected exactly three columns.")
                try:
                    rows.append(self.validate_sample(row["sensor"], row["value"], row["observed_at"]))
                except ValidationError as error:
                    raise ValidationError(f"Line {line}: {error}") from None
        except csv.Error as error:
            raise ValidationError(f"Invalid CSV: {error}") from None
        if not rows:
            raise ValidationError("CSV contains no samples.")
        accepted = sum(self.insert_sample(db, row, "import") for row in rows)
        self.trim_samples(db)
        self.event(db, "info", "import", f"Imported {accepted} samples; skipped {len(rows)-accepted} duplicates.")
        return {"message": f"Imported {accepted} samples; skipped {len(rows)-accepted} duplicates.", "accepted": accepted}

    def demo_reset(self, db, data):
        if not self.demo or data.get("confirmation") != "RESET DEMO":
            raise ValidationError("Reset is available only in the separate demo workspace.", 403)
        for table in ("completions", "tasks", "inventory", "reports", "cases", "samples", "events", "settings", "operations"):
            db.execute(f"DELETE FROM {table}")
        self.seed(db)
        self.last_sample = 0
        return {"message": "Demo workspace reset. Saved workspace was not touched."}

    def tick(self):
        now = self.clock()
        with self.store.transaction() as db:
            if setting(db, "feed") and now - self.last_sample >= 2:
                fault = setting(db, "fault")
                for index, (sensor, limits) in enumerate(SENSORS.items()):
                    if fault == "missing" and sensor == "airflow":
                        continue
                    value = round(limits["base"] + math.sin(now / 13 + index) * 1.8, 1)
                    observed = now
                    if sensor == "airflow":
                        if fault == "low_airflow":
                            value = 61.0 + round(math.sin(now / 7), 1)
                        elif fault == "corrupt":
                            value = float("nan")
                        elif fault == "delayed":
                            observed = now - 90
                    try:
                        sample = self.validate_sample(sensor, value, observed)
                        self.insert_sample(db, sample, "simulator")
                    except ValidationError:
                        self.event(db, "warning", "telemetry", f"Rejected corrupt {sensor} sample; last valid reading retained.")
                self.trim_samples(db)
                self.last_sample = now
            if not setting(db, "online"):
                return
            rows = db.execute("SELECT * FROM reports WHERE status != 'delivered' ORDER BY created LIMIT 100").fetchall()
            for report in rows:
                if report["status"] in ("queued", "retry") and report["next_at"] <= now:
                    delay = setting(db, "delay")
                    db.execute("UPDATE reports SET status='in_flight', attempts=attempts+1, ack_at=? WHERE id=?",
                               (now + delay * 2, report["id"]))
                    self.event(db, "info", "outbox", f"Transmitted {report['id'][:8]} to the simulated ground endpoint.")
                elif report["status"] == "in_flight" and report["ack_at"] <= now:
                    if setting(db, "drop_ack"):
                        set_setting(db, "drop_ack", False)
                        backoff = min(60, 2 ** min(report["attempts"], 6))
                        db.execute("UPDATE reports SET status='retry', next_at=?, ack_at=NULL WHERE id=?",
                                   (now + backoff, report["id"]))
                        self.event(db, "warning", "outbox", f"Acknowledgement lost for {report['id'][:8]}; retry in {backoff}s.")
                    else:
                        receipt = "SIM-" + report["id"][:8].upper()
                        db.execute("UPDATE reports SET status='delivered', receipt=? WHERE id=?", (receipt, report["id"]))
                        self.event(db, "info", "outbox", f"Simulated receipt {receipt} acknowledged.")

    def snapshot(self):
        now = self.clock()
        with self.store.transaction() as db:
            config = {row["key"]: json.loads(row["value"]) for row in db.execute("SELECT * FROM settings")}
            tasks = []
            for task in TASKS:
                saved = dict(db.execute("SELECT * FROM tasks WHERE id=?", (task["id"],)).fetchone())
                saved["checks"] = json.loads(saved["checks"])
                item = {**task, **saved}
                item["due_in"] = item["last_day"] + item["interval"] - config["day"]
                tasks.append(item)
            stock = []
            for item in SPARES:
                saved = dict(db.execute("SELECT * FROM inventory WHERE id=?", (item[0],)).fetchone())
                stock.append({**saved, "name": item[1], "location": item[2], "minimum": item[4], "unit": item[5]})
            sensors = []
            for key, limits in SENSORS.items():
                rows = [dict(r) for r in db.execute("SELECT * FROM samples WHERE sensor=? ORDER BY observed DESC LIMIT 40", (key,))]
                latest = rows[0] if rows else None
                age = max(0, now - latest["observed"]) if latest else None
                quality = "missing" if not latest else "stale" if age > 12 else "warning" if not limits["low"] <= latest["value"] <= limits["high"] else "nominal"
                sensors.append({"id": key, **limits, "latest": latest, "age": age, "quality": quality,
                                "history": list(reversed(rows))})
            counts = dict(db.execute("SELECT status, COUNT(*) FROM reports GROUP BY status").fetchall())
            return {"settings": config, "tasks": sorted(tasks, key=lambda x: x["due_in"]),
                    "inventory": stock, "sensors": sensors, "trees": TREES,
                    "reports": [dict(r) for r in db.execute("SELECT * FROM reports ORDER BY created DESC LIMIT 100")],
                    "report_counts": counts, "now": now, "demo": self.demo,
                    "cases": [dict(r) for r in db.execute("SELECT * FROM cases ORDER BY created DESC LIMIT 30")],
                    "events": [dict(r) for r in db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 100")],
                    "completions": [dict(r) for r in db.execute("SELECT * FROM completions ORDER BY id DESC LIMIT 30")],
                    "data_path": str(self.store.path)}

    def export(self, kind):
        tables = {"reports": "reports", "telemetry": "samples", "history": "events", "completions": "completions", "cases": "cases"}
        if kind not in tables:
            raise ValidationError("Unknown export type.", 404)
        with self.store.transaction() as db:
            cursor = db.execute(f"SELECT * FROM {tables[kind]} ORDER BY rowid")
            stream = io.StringIO(newline="")
            writer = csv.writer(stream)
            writer.writerow([c[0] for c in cursor.description])
            for row in cursor:
                # Keep spreadsheet programs from interpreting untrusted notes as formulas.
                writer.writerow(["'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value for value in row])
            return stream.getvalue().encode("utf-8-sig")
