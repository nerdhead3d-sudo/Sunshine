import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from pet import settings_store


class SettingsStoreTests(unittest.TestCase):
    def test_save_then_load_round_trips_without_deadlocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            with mock.patch.object(settings_store, "_SETTINGS_PATH", path), \
                    mock.patch.object(settings_store.config, "DATA_DIR", Path(tmp)):
                done = threading.Event()

                def run():
                    settings_store.save({"language": "en"})
                    done.set()

                threading.Thread(target=run, daemon=True).start()
                self.assertTrue(done.wait(3), "save() deadlocked")
                self.assertEqual(settings_store.load()["language"], "en")


if __name__ == "__main__":
    unittest.main()
