"""Checks for data-only update plans and interrupted-release recovery."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import automation


class UpdatePlanTests(unittest.TestCase):
    def setUp(self):
        self.current = {"version_code": 1, "version_name": "0.1.0"}
        self.version = {
            "version_code": 2, "version_name": "1.23.0-android.2",
            "automated": True, "release_tag": "v1.23.0-android.2", "upstream_sha": "b" * 40,
        }
        self.plan = {
            "schema": 1, "base_sha": "a" * 40, "upstream_sha": "b" * 40,
            "publish": True, "resume": False, "release_tag": self.version["release_tag"],
            "version": self.version, "files": {"version.json": json.dumps(self.version)},
        }

    def test_monotonic_version(self):
        automation.validate_plan(self.plan, self.current)
        self.plan["version"]["version_code"] = 1
        self.plan["files"]["version.json"] = json.dumps(self.plan["version"])
        with self.assertRaises(AssertionError):
            automation.validate_plan(self.plan, self.current)

    def test_workflow_and_traversal_changes_are_rejected(self):
        for path in (".github/workflows/update-release.yml", "../outside", "/tmp/outside"):
            value = copy.deepcopy(self.plan)
            value["files"][path] = "untrusted"
            with self.assertRaises(AssertionError):
                automation.validate_plan(value, self.current)

    def test_python_options_and_urls_are_rejected(self):
        for dependency in ("--index-url https://example.invalid", "thing @ https://example.invalid/code", "-r other.txt"):
            value = copy.deepcopy(self.plan)
            value["files"]["app/requirements-android.txt"] = dependency
            with self.assertRaises(AssertionError):
                automation.validate_plan(value, self.current)

    def test_only_exact_zipapp_checksum_is_accepted(self):
        checksum = "f" * 64
        self.assertEqual(automation.checksum_for_zipapp(checksum + "  yt-dlp\n"), checksum)
        for text in (checksum + "  yt-dlp.exe\n", "bad  yt-dlp\n", (checksum + "  yt-dlp\n") * 2):
            with self.assertRaises(AssertionError):
                automation.checksum_for_zipapp(text)

    def test_untagged_draft_is_found_for_retry(self):
        draft = {"tag_name": "v1.23.0-android.2", "draft": True}
        with patch.object(automation, "api", side_effect=[None, [draft]]) as request:
            self.assertEqual(automation.find_release(draft["tag_name"]), draft)
        self.assertEqual(request.call_count, 2)

    def test_successful_run_is_not_published_twice(self):
        self.version["automation_run_id"] = "123"
        with patch.object(automation, "read_json", return_value=self.version), \
             patch.object(automation, "git", side_effect=["a" * 40, "160000 commit " + "b" * 40 + "\tupstream"]), \
             patch.object(automation, "api", return_value={"draft": False}), \
             patch.dict(automation.os.environ, {"GITHUB_RUN_ID": "123"}):
            self.assertFalse(automation.make_plan(force=True)["publish"])

    def test_resume_keeps_existing_version(self):
        self.plan["resume"] = True
        self.plan["files"] = {}
        automation.validate_plan(self.plan, self.version)

    def test_interrupted_publication_resumes_without_resolving_upstream(self):
        with patch.object(automation, "read_json", return_value=self.version), \
             patch.object(automation, "git", side_effect=["a" * 40, "160000 commit " + "b" * 40 + "\tupstream"]), \
             patch.object(automation, "api", return_value={"draft": True}) as request:
            plan = automation.make_plan()
        self.assertTrue(plan["publish"])
        self.assertTrue(plan["resume"])
        self.assertEqual(plan["version"]["version_code"], 2)
        self.assertEqual(request.call_count, 1)


if __name__ == "__main__":
    unittest.main()
