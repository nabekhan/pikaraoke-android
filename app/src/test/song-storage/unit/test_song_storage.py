"""Deletion policy tests use only isolated temporary song folders."""

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[5] / "app/build/generated/python"
spec = importlib.util.spec_from_file_location(
    "song_storage", ROOT / "pikaraoke/lib/song_storage.py"
)
storage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(storage)
MEDIA = {".mp3", ".mp4", ".zip", ".mkv", ".avi", ".webm", ".mov"}


class SongStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.songs = self.base / "songs"
        self.songs.mkdir()

    def file(self, name, size=10, age=1):
        path = self.songs / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * size)
        os.utime(path, (age, age))
        return path

    def prune(self, limit):
        return storage.prune_songs(self.songs, limit, MEDIA)

    def test_disabled_and_invalid_limits_never_delete(self):
        song = self.file("keep.mp4")
        for limit in (0, -1, True, False, "nan", "inf", "1.2", "", storage.MAX_BYTES + 1):
            with self.subTest(limit=limit), patch.object(storage, "_scan") as scan:
                result = self.prune(limit)
                self.assertEqual(result["removed_files"], 0)
                scan.assert_not_called()
                self.assertTrue(song.exists())

    def test_unreadable_subtree_aborts_before_any_deletion(self):
        song = self.file("keep.mp4", 20)

        def unreadable(*args, **kwargs):
            kwargs["onerror"](PermissionError("unreadable subtree"))
            return iter(())

        with patch.object(storage.os, "fwalk", side_effect=unreadable):
            result = self.prune(1)
        self.assertTrue(result["error"])
        self.assertEqual(result["removed_files"], 0)
        self.assertTrue(song.exists())

    def test_no_journal_needs_no_song_folder(self):
        database = Mock()
        self.assertEqual(
            storage.reconcile_journal(
                self.base / "missing", self.base / "no-journal.json", database
            ),
            0,
        )
        database.delete_by_paths.assert_not_called()

    def test_two_song_folders_have_independent_pending_journals(self):
        second = self.base / "second"
        second.mkdir()
        journal_a = storage.cleanup_journal_path(str(self.base), str(self.songs))
        journal_b = storage.cleanup_journal_path(str(self.base), str(second))
        self.assertNotEqual(journal_a, journal_b)
        self.file("old.mp4", 20)
        (second / "old.mp4").write_bytes(b"x" * 20)
        for root, journal in ((self.songs, journal_a), (second, journal_b)):
            result = storage.prune_songs(root, 1, MEDIA, journal)
            self.assertEqual(result["removed_files"], 1)
            self.assertTrue(Path(journal).exists())
        database = Mock()
        self.assertEqual(storage.reconcile_journal(self.songs, journal_a, database), 1)
        self.assertTrue(Path(journal_b).exists())
        self.assertEqual(storage.reconcile_journal(second, journal_b, database), 1)

    def test_at_or_below_limit_keeps_every_song(self):
        song = self.file("keep.mp4", 20)
        for limit in (20, 21):
            self.assertEqual(self.prune(limit)["removed_files"], 0)
            self.assertTrue(song.exists())

    def test_removes_only_oldest_songs_needed_to_reach_limit(self):
        old = self.file("old.mp4", age=1)
        middle = self.file("middle.mp4", age=2)
        new = self.file("new.mp4", age=3)
        result = self.prune(20)
        self.assertFalse(old.exists())
        self.assertTrue(middle.exists() and new.exists())
        self.assertEqual((result["before_bytes"], result["after_bytes"]), (30, 20))

    def test_nested_case_insensitive_companions_and_variants_removed_together(self):
        bundle = [
            self.file("folder/Song.MP3", 10),
            self.file("folder/song.CDG", 3),
            self.file("folder/song.mcg", 2),
            self.file("folder/SONG.ass", 1),
            self.file("folder/song.mp4", 4),
        ]
        new = self.file("new.zip", 10, age=2)
        result = self.prune(10)
        self.assertTrue(all(not path.exists() for path in bundle))
        self.assertTrue(new.exists())
        self.assertEqual(result["removed_bytes"], 20)

    def test_recent_companion_protects_recently_updated_song(self):
        audio = self.file("updated.mp3", age=1)
        graphics = self.file("updated.cdg", age=10)
        old = self.file("older.mp4", age=5)
        self.prune(20)
        self.assertTrue(audio.exists() and graphics.exists())
        self.assertFalse(old.exists())

    def test_unrelated_and_incomplete_files_count_but_are_not_deleted(self):
        protected = [
            self.file("download.mp4.part", 10),
            self.file("notes.txt", 10),
            self.file(".hidden.mp4", 10),
            self.file(".private/song.mp4", 10),
            self.file("orphan.cdg", 10),
        ]
        song = self.file("old.mp4", 10)
        result = self.prune(1)
        self.assertFalse(song.exists())
        self.assertTrue(all(path.exists() for path in protected))
        self.assertEqual(result["after_bytes"], 50)

    def test_symlinks_never_delete_outside_files(self):
        outside = self.base / "outside"
        outside.mkdir()
        victim = outside / "song.mp4"
        victim.write_bytes(b"outside")
        (self.songs / "linked.mp4").symlink_to(victim)
        (self.songs / "linked-folder").symlink_to(outside, target_is_directory=True)
        old = self.file("old.mp4", 10)
        self.prune(1)
        self.assertFalse(old.exists())
        self.assertEqual(victim.read_bytes(), b"outside")
        link = self.base / "root-link"
        link.symlink_to(outside, target_is_directory=True)
        self.assertTrue(storage.prune_songs(link, 1, MEDIA)["error"])
        self.assertTrue(victim.exists())

    def test_changed_file_aborts_before_deleting_newer_songs(self):
        old = self.file("old.mp4")
        new = self.file("new.mp4", age=2)
        original_scan = storage._scan

        def changed(*args):
            result = original_scan(*args)
            old.write_bytes(b"replacement")
            return result

        with patch.object(storage, "_scan", side_effect=changed):
            result = self.prune(1)
        self.assertTrue(result["error"])
        self.assertEqual(old.read_bytes(), b"replacement")
        self.assertTrue(new.exists())

    def test_replaced_directory_cannot_redirect_deletion_outside_root(self):
        self.file("nested/song.mp4")
        outside = self.base / "outside"
        outside.mkdir()
        victim = outside / "song.mp4"
        victim.write_bytes(b"outside")
        original_scan = storage._scan

        def changed(*args):
            result = original_scan(*args)
            (self.songs / "nested").rename(self.songs / "moved")
            (self.songs / "nested").symlink_to(outside, target_is_directory=True)
            return result

        with patch.object(storage, "_scan", side_effect=changed):
            self.assertTrue(self.prune(1)["error"])
        self.assertEqual(victim.read_bytes(), b"outside")

    def test_scan_failure_deletes_nothing(self):
        song = self.file("keep.mp4")
        with patch.object(storage, "_scan", side_effect=PermissionError("test")):
            self.assertTrue(self.prune(1)["error"])
        self.assertTrue(song.exists())

    def test_failed_media_deletion_keeps_companions_and_newer_songs(self):
        paths = [self.file("old.mp3"), self.file("old.cdg"), self.file("new.mp4", age=2)]
        with patch.object(storage.os, "unlink", side_effect=PermissionError("test")):
            result = self.prune(1)
        self.assertTrue(result["error"])
        self.assertEqual(result["removed_files"], 0)
        self.assertTrue(all(path.exists() for path in paths))

    def test_companion_failure_is_reported_without_deleting_newer_song(self):
        audio = self.file("old.mp3")
        graphics = self.file("old.cdg")
        new = self.file("new.mp4", age=2)
        original_unlink = os.unlink

        def fail_companion(name, **kwargs):
            if name == "old.cdg":
                raise PermissionError("test")
            return original_unlink(name, **kwargs)

        with patch.object(storage.os, "unlink", side_effect=fail_companion):
            result = self.prune(1)
        self.assertTrue(result["error"])
        self.assertFalse(audio.exists())
        self.assertTrue(graphics.exists() and new.exists())
        self.assertEqual((result["removed_files"], result["after_bytes"]), (1, 20))

    def test_journal_recovers_after_file_deletion_before_database_commit(self):
        old = self.file("old.mp4")
        kept = self.file("new.mp4", age=2)
        journal = self.base / "cleanup.json"
        storage.prune_songs(self.songs, 10, MEDIA, journal)
        self.assertFalse(old.exists())
        self.assertTrue(kept.exists() and journal.exists())
        database = Mock()
        database.delete_by_paths.side_effect = RuntimeError("interrupted DB transaction")
        with self.assertRaises(RuntimeError):
            storage.reconcile_journal(self.songs, journal, database)
        self.assertTrue(journal.exists())
        self.prune(0)
        database.delete_by_paths.side_effect = None
        self.assertEqual(storage.reconcile_journal(self.songs, journal, database), 1)
        database.delete_by_paths.assert_called_with([str(old)])
        self.assertFalse(journal.exists())
        self.assertTrue(kept.exists())

    def test_pending_intents_are_merged_and_existing_files_keep_database_rows(self):
        old = self.file("old.mp4")
        new = self.file("new.mp4", age=2)
        journal = self.base / "cleanup.json"
        missing = self.songs / "previous.mp4"
        journal.write_text(
            json.dumps({"root": str(self.songs), "paths": ["previous.mp4", "new.mp4"]})
        )
        storage.prune_songs(self.songs, 10, MEDIA, journal)
        database = Mock()
        storage.reconcile_journal(self.songs, journal, database)
        self.assertEqual(set(database.delete_by_paths.call_args.args[0]), {str(missing), str(old)})
        self.assertTrue(new.exists())

    def test_failed_journal_write_prevents_any_deletion(self):
        song = self.file("old.mp4")
        with patch.object(storage, "_record_intent", side_effect=OSError("disk full")):
            result = storage.prune_songs(self.songs, 1, MEDIA, self.base / "cleanup.json")
        self.assertTrue(result["error"])
        self.assertTrue(song.exists())

    def test_journal_rejects_traversal_or_different_root(self):
        journal = self.base / "cleanup.json"
        database = Mock()
        for value in (
            {"root": str(self.songs), "paths": ["../outside.mp4"]},
            {"root": str(self.base), "paths": ["missing.mp4"]},
        ):
            journal.write_text(json.dumps(value))
            with self.assertRaises(OSError):
                storage.reconcile_journal(self.songs, journal, database)
        database.delete_by_paths.assert_not_called()

    def test_parse_limit_accepts_only_safe_non_negative_integers(self):
        self.assertEqual(storage.parse_limit("1500000000"), 1500000000)
        for value in ("-1", "True", "nan", str(storage.MAX_BYTES + 1)):
            with self.assertRaises(ValueError):
                storage.parse_limit(value)


if __name__ == "__main__":
    unittest.main()
