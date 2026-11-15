import tempfile
import unittest
from pathlib import Path

from msc_logger.engine import Engine
from msc_logger.storage import Store
from scripts.recover import restore


class RecoveryTests(unittest.TestCase):
    def test_restore_preserves_previous_database_and_recovers_report(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "workspace.sqlite3"
            store = Store(path)
            engine = Engine(store)
            engine.command("report", {"operation_id": "one", "category": "Other", "description": "Recover me", "priority": "routine"})
            backup = store.backup(Path(folder) / "saved.sqlite3")
            store.close()
            path.write_bytes(b"damaged database")
            archive = restore(backup, folder, "workspace")
            self.assertEqual((archive / path.name).read_bytes(), b"damaged database")
            store = Store(path)
            try:
                self.assertEqual(Engine(store).snapshot()["reports"][0]["description"], "Recover me")
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
