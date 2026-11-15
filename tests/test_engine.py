"""Behavioral tests use an injected clock, never real waiting."""

from contextlib import closing
import concurrent.futures
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path

from msc_logger.engine import Engine, ValidationError
from msc_logger.storage import Store


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "workspace.sqlite3"
        self.now = 1800000000.0
        self.store = Store(self.path)
        self.engine = Engine(self.store, clock=lambda: self.now, demo=True)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def command(self, name, **data):
        return self.engine.command(name, {"operation_id": str(uuid.uuid4()), **data})

    def report(self, **extra):
        return self.command("report", category="Equipment", description="Device unresponsive", priority="routine", **extra)

    def test_checklist_required_and_duplicate_completion_blocked(self):
        task = self.engine.snapshot()["tasks"][0]
        data = {"id": task["id"], "day": 1, "last_day": task["last_day"]}
        with self.assertRaises(ValidationError):
            self.command("task_complete", **data, operator="Alex", note="")
        self.command("task_progress", **data, checks=[True] * len(task["steps"]))
        self.command("task_complete", **data, operator="Alex", note="Checked")
        with self.assertRaises(ValidationError):
            self.command("task_complete", **data, operator="Alex", note="Checked")
        self.assertEqual(len(self.engine.snapshot()["completions"]), 1)

    def test_checklist_survives_restart(self):
        task = self.engine.snapshot()["tasks"][0]
        checks = [True] + [False] * (len(task["steps"]) - 1)
        self.command("task_progress", id=task["id"], day=1, last_day=task["last_day"], checks=checks)
        self.store.close()
        self.store = Store(self.path)
        self.engine = Engine(self.store, clock=lambda: self.now, demo=True)
        self.assertEqual(self.engine.snapshot()["tasks"][0]["checks"], checks)

    def test_new_day_invalidates_open_checklist(self):
        task = self.engine.snapshot()["tasks"][0]
        self.command("settings", advance_day=True)
        with self.assertRaises(ValidationError):
            self.command("task_progress", id=task["id"], day=1, last_day=task["last_day"], checks=[True] * len(task["steps"]))

    def test_idempotent_reports_and_mismatched_replays(self):
        data = dict(operation_id="unique-operation", category="Equipment", description="Observation", priority="routine")
        first = self.engine.command("report", data)
        second = self.engine.command("report", data)
        self.assertEqual(first, second)
        self.assertEqual(len(self.engine.snapshot()["reports"]), 1)
        with self.assertRaises(ValidationError):
            self.engine.command("report", {**data, "description": "Changed"})

    def test_inventory_negative_and_stale_changes_blocked(self):
        self.command("inventory", id="hex", revision=0, delta=-1, reason="Crew A checkout")
        with self.assertRaises(ValidationError):
            self.command("inventory", id="hex", revision=0, delta=-1, reason="Crew B stale checkout")
        with self.assertRaises(ValidationError):
            self.command("inventory", id="hex", revision=1, delta=-5, reason="Too many")
        self.assertEqual(self.engine.snapshot()["inventory"][2]["quantity"], 1)

    def test_concurrent_inventory_adjustments_have_one_winner(self):
        def adjust(_):
            try:
                self.command("inventory", id="hex", revision=0, delta=-1, reason="Concurrent checkout")
                return True
            except ValidationError:
                return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(adjust, range(8)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(self.engine.snapshot()["inventory"][2]["quantity"], 1)

    def test_offline_queue_and_delayed_acknowledgement(self):
        self.report()
        self.engine.tick()
        self.assertEqual(self.engine.snapshot()["reports"][0]["status"], "queued")
        self.command("settings", online=True)
        self.engine.tick()
        self.assertEqual(self.engine.snapshot()["reports"][0]["status"], "in_flight")
        self.now += 7
        self.engine.tick()
        self.assertEqual(self.engine.snapshot()["reports"][0]["status"], "in_flight")
        self.now += 1
        self.engine.tick()
        self.assertTrue(self.engine.snapshot()["reports"][0]["receipt"].startswith("SIM-"))

    def test_outage_and_restart_preserve_inflight_report(self):
        self.report()
        self.command("settings", online=True)
        self.engine.tick()
        self.command("settings", online=False)
        self.now += 100
        self.store.close()
        self.store = Store(self.path)
        self.engine = Engine(self.store, clock=lambda: self.now)
        self.engine.tick()
        self.assertEqual(self.engine.snapshot()["reports"][0]["status"], "in_flight")
        self.command("settings", online=True)
        self.engine.tick()
        self.assertEqual(self.engine.snapshot()["reports"][0]["status"], "delivered")

    def test_lost_ack_retries_once_with_same_receipt_identity(self):
        report_id = self.report()["id"]
        self.command("settings", online=True, drop_ack=True)
        self.engine.tick()
        self.now += 8
        self.engine.tick()
        self.assertEqual(self.engine.snapshot()["reports"][0]["status"], "retry")
        self.now += 2
        self.engine.tick()
        self.now += 8
        self.engine.tick()
        row = self.engine.snapshot()["reports"][0]
        self.assertEqual(row["status"], "delivered")
        self.assertEqual(row["attempts"], 2)
        self.assertEqual(row["receipt"], "SIM-" + report_id[:8].upper())

    def test_corrupt_data_retains_last_reading_then_stales(self):
        self.engine.tick()
        original = self.engine.snapshot()["sensors"][0]["latest"]
        self.command("settings", fault="corrupt")
        self.now += 15
        self.engine.tick()
        sensor = self.engine.snapshot()["sensors"][0]
        self.assertEqual(sensor["latest"], original)
        self.assertEqual(sensor["quality"], "stale")
        self.assertTrue(any("Rejected corrupt" in e["message"] for e in self.engine.snapshot()["events"]))

    def test_missing_and_delayed_samples_do_not_replace_newer_data(self):
        self.engine.tick()
        observed = self.engine.snapshot()["sensors"][0]["latest"]["observed"]
        self.command("settings", fault="delayed")
        self.now += 2
        self.engine.tick()
        self.assertEqual(self.engine.snapshot()["sensors"][0]["latest"]["observed"], observed)
        self.command("settings", fault="missing")
        self.now += 15
        self.engine.tick()
        self.assertEqual(self.engine.snapshot()["sensors"][0]["quality"], "stale")

    def test_warning_threshold_and_recovery(self):
        self.command("settings", fault="low_airflow")
        self.engine.tick()
        self.assertEqual(self.engine.snapshot()["sensors"][0]["quality"], "warning")
        self.command("settings", fault="normal")
        self.now += 2
        self.engine.tick()
        self.assertEqual(self.engine.snapshot()["sensors"][0]["quality"], "nominal")

    def test_import_is_atomic_and_duplicates_are_skipped(self):
        header = "sensor,value,observed_at\n"
        with self.assertRaises(ValidationError):
            self.command("import", csv=header + f"airflow,90,{self.now}\nhumidity,NaN,{self.now}\n")
        self.assertIsNone(self.engine.snapshot()["sensors"][0]["latest"])
        content = header + f"airflow,90,{self.now}\nairflow,90,{self.now}\n"
        self.assertEqual(self.command("import", csv=content)["accepted"], 1)
        self.assertEqual(self.command("import", csv=content)["accepted"], 0)

    def test_future_nonfinite_and_bad_types_rejected(self):
        for value in ("NaN", "Infinity", -100, None, True):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.engine.validate_sample("airflow", value, self.now)
        with self.assertRaises(ValidationError):
            self.engine.validate_sample("airflow", 90, self.now + 100)
        with self.assertRaises(ValidationError):
            self.command("settings", online="yes")

    def test_urgent_case_escalates_atomically(self):
        with self.assertRaises(ValidationError):
            self.command("case", tree="equipment", choice=1, outcome="resolved", note="Smoke")
        self.command("case", tree="equipment", choice=1, outcome="escalated", note="Training smoke observation")
        snapshot = self.engine.snapshot()
        self.assertEqual(len(snapshot["cases"]), 1)
        self.assertEqual(snapshot["reports"][0]["priority"], "urgent")
        self.assertIn("Heat, smoke", snapshot["reports"][0]["context"])

    def test_spreadsheet_export_neutralizes_formula(self):
        self.command("report", category="Other", description="=HYPERLINK(\"bad\")", priority="routine")
        exported = self.engine.export("reports").decode("utf-8-sig")
        self.assertIn("'=HYPERLINK", exported)

    def test_backup_is_consistent_and_readable(self):
        self.report()
        target = self.store.backup(Path(self.temp.name) / "backup.sqlite3")
        with closing(sqlite3.connect(target)) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM reports").fetchone()[0], 1)

    def test_corrupted_database_is_not_replaced(self):
        damaged = Path(self.temp.name) / "damaged.sqlite3"
        content = b"not a database" * 50
        damaged.write_bytes(content)
        with self.assertRaises(sqlite3.DatabaseError):
            Store(damaged)
        self.assertEqual(damaged.read_bytes(), content)

    def test_reset_requires_demo_profile_and_confirmation(self):
        self.report()
        self.engine.demo = False
        with self.assertRaises(ValidationError):
            self.command("demo_reset", confirmation="RESET DEMO")
        self.assertEqual(len(self.engine.snapshot()["reports"]), 1)
        self.engine.demo = True
        self.command("demo_reset", confirmation="RESET DEMO")
        self.assertEqual(self.engine.snapshot()["reports"], [])

    def test_retention_bounds_samples(self):
        with self.store.transaction() as db:
            for index in range(1050):
                self.engine.insert_sample(db, ("airflow", 90, self.now - index), "test")
            self.engine.trim_samples(db)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM samples").fetchone()[0], 1000)
            self.assertEqual(db.execute("SELECT MIN(observed) FROM samples").fetchone()[0], self.now - 999)


if __name__ == "__main__":
    unittest.main()
