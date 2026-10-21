"""Android-owned validation coverage for the storage preference."""

import sys
import tempfile
import unittest
from pathlib import Path


GENERATED = Path(__file__).resolve().parents[5] / "app/build/generated/python"
sys.path.insert(0, str(GENERATED))

from pikaraoke.lib.preference_manager import PreferenceManager


class SongStoragePreferencesTest(unittest.TestCase):
    def test_limit_is_stored_as_valid_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            config = str(Path(directory) / "config.ini")
            preferences = PreferenceManager(config)
            for value in ("-1", "False", "nan", "1.2", str(2**53)):
                self.assertFalse(preferences.set("max_song_storage_bytes", value)[0])
            self.assertTrue(preferences.set("max_song_storage_bytes", "1500000000")[0])
            self.assertEqual(preferences.get_or_default("max_song_storage_bytes"), 1500000000)
            Path(config).write_text(
                "[USERPREFERENCES]\nmax_song_storage_bytes=invalid\n", encoding="utf-8"
            )
            self.assertEqual(PreferenceManager(config).get_or_default("max_song_storage_bytes"), 0)
