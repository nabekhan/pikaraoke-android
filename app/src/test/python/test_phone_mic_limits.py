"""Admission and Settings changes must agree on the current microphone limit."""

import json
import sys
import threading
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from flask import Flask
from flask_babel import Babel

# Load the real preferences and bridge without PiKaraoke's eager desktop
# Karaoke import. This is a host-side admission test, with no Android runtime.
ROOT = Path(__file__).resolve().parents[4]
package = types.ModuleType("pikaraoke")
package.__path__ = [str(ROOT / "upstream/pikaraoke")]
auth = types.ModuleType("pikaraoke.lib.auth")
auth.public = lambda view: view
with patch.dict(sys.modules, {"pikaraoke": package, "pikaraoke.lib.auth": auth}):
    from android_runtime import phone_mics as bridge
    from pikaraoke.lib.phone_mics import PhoneMicError
    from pikaraoke.lib.preference_manager import PreferenceManager


class PhoneMicLimitTest(TestCase):
    def test_lowering_limit_cannot_be_overwritten_by_an_inflight_join(self):
        """A join started first completes before the lower limit is saved, never after."""
        with TemporaryDirectory() as directory:
            self._check_limit(Path(directory))

    def _check_limit(self, directory):
        preferences = PreferenceManager(str(directory / "config.ini"))
        assert preferences.set("max_phone_mics", 4)[0]
        app = Flask(__name__)
        Babel(app)
        app.config["KARAOKE_INSTANCE"] = SimpleNamespace(preferences=preferences)
        backend = bridge._AndroidBackend(app)
        entered, release, writing, saved = (threading.Event() for _ in range(4))

        class Host:
            limit, active = 4, 1

            def setMaxMics(self, limit):
                if limit == 4:
                    entered.set()
                    assert release.wait(2)
                self.limit = limit

            def join(self, _name):
                if self.active >= self.limit:
                    raise RuntimeError("Full")
                self.active += 1
                return json.dumps({"max": self.limit})

        host = Host()

        def lower_limit():
            writing.set()
            with app.app_context():
                result = preferences.set("max_phone_mics", 1)
            saved.set()
            return result

        with patch.object(bridge, "_host", return_value=host):
            with ThreadPoolExecutor(max_workers=2) as pool:
                join = pool.submit(backend.call, "join", "Singer")
                try:
                    assert entered.wait(2)
                    update = pool.submit(lower_limit)
                    assert writing.wait(2)
                    self.assertFalse(
                        saved.wait(0.1), "Settings must not finish while a stale join can still run"
                    )
                finally:
                    release.set()
                assert join.result(timeout=2) == {"max": 4}
                assert update.result(timeout=2)[0]
            assert preferences.get_or_default("max_phone_mics") == 1
            with self.assertRaises(PhoneMicError) as error:
                backend.call("join", "Another singer")
            assert error.exception.status_code == 409
            assert host.limit == 1
            assert host.active == 2  # Existing singers stay connected.
