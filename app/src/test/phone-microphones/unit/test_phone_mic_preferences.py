"""Android-owned phone-microphone preference coverage."""

import sys
import tempfile
import unittest
from pathlib import Path


GENERATED = Path(__file__).resolve().parents[5] / "app/build/generated/python"
sys.path.insert(0, str(GENERATED))

from pikaraoke.lib.preference_manager import PreferenceManager


class PhoneMicPreferencesTest(unittest.TestCase):
    def test_limit_is_validated_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            config = str(Path(directory) / "config.ini")
            preferences = PreferenceManager(config)
            self.assertEqual(preferences.get_or_default("max_phone_mics"), 2)
            for value in (0, 5, -1, True, False, "true", "nan", "2.5", 2.0):
                self.assertFalse(preferences.set("max_phone_mics", value)[0])
            for value in ("1", "4", "2"):
                self.assertTrue(preferences.set("max_phone_mics", value)[0])
                self.assertEqual(
                    PreferenceManager(config).get_or_default("max_phone_mics"), int(value)
                )
            Path(config).write_text("[USERPREFERENCES]\nmax_phone_mics=9\n", encoding="utf-8")
            target = type("Target", (), {})()
            restored = PreferenceManager(config, target=target)
            self.assertEqual(restored.get_or_default("max_phone_mics"), 2)
            restored.apply_all()
            self.assertEqual(target.max_phone_mics, 2)
