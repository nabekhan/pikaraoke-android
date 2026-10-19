"""Checks for data-only update plans and interrupted-release recovery."""
import copy
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import automation
import release_android


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

    def test_duplicate_drafts_across_pages_are_rejected(self):
        draft = {"tag_name": "v1.23.0-android.2", "draft": True}
        first_page = [draft] + [{"tag_name": "other"} for _ in range(99)]
        with patch.object(automation, "api", side_effect=[None, first_page, [draft]]):
            with self.assertRaises(AssertionError):
                automation.find_release(draft["tag_name"])

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

    def test_latest_mismatch_plans_repair_without_building_or_resolving_upstream(self):
        metadata = {"state": "uploaded", "size": 100, "digest": "sha256:" + "f" * 64}
        existing = {"id": 7, "draft": False, "prerelease": False, "assets": [
            dict(metadata, name="app.apk"),
            dict(metadata, name=f"pikaraoke-tv-{self.version['version_name']}-universal.apk")]}
        with patch.object(automation, "read_json", return_value=self.version), \
             patch.object(automation, "git", side_effect=["a" * 40, "160000 commit " + "b" * 40 + "\tupstream"]), \
             patch.object(automation, "find_release", return_value=existing), \
             patch.object(automation, "api", return_value={"id": 8}) as request:
            plan = automation.make_plan(force=True)
        self.assertTrue(plan["repair_latest"])
        self.assertFalse(plan["publish"])
        self.assertEqual(plan["version"], self.version)
        self.assertEqual(request.call_count, 1)

    def test_missing_published_alias_fails_before_successful_rerun_exit(self):
        self.version.update(universal_apk_alias=True, automation_run_id="123")
        with patch.object(automation, "read_json", return_value=self.version), \
             patch.object(automation, "git", side_effect=["a" * 40, "160000 commit " + "b" * 40 + "\tupstream"]), \
             patch.object(automation, "find_release", return_value={"draft": False, "assets": []}), \
             patch.dict(automation.os.environ, {"GITHUB_RUN_ID": "123"}):
            with self.assertRaisesRegex(AssertionError, "download is missing"):
                automation.make_plan()

    def test_repair_cannot_include_an_update(self):
        value = copy.deepcopy(self.plan)
        value["repair_latest"] = True
        with self.assertRaises(AssertionError):
            automation.validate_plan(value, self.current)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.signed = self.root / "signed"
        self.signed.mkdir()
        self.base = "a" * 40
        self.version = {"automated": True, "version_code": 9, "version_name": "1.23.0-android.9",
                        "release_tag": "v1.23.0-android.9", "upstream_sha": "b" * 40}
        self.plan = {"schema": 1, "base_sha": self.base, "upstream_sha": "b" * 40,
                     "publish": True, "resume": False, "release_tag": self.version["release_tag"],
                     "version": self.version, "files": {"version.json": json.dumps(self.version)}}
        records = []
        for abi in release_android.ABIS:
            path = self.signed / f"pikaraoke-tv-{self.version['version_name']}-{abi}.apk"
            path.write_bytes(b"signed fixture for " + abi.encode())
            records.append({"name": path.name, "bytes": path.stat().st_size, "sha256": release_android.digest(path)})
        report = {"certificate_sha256": release_android.CERTIFICATE, "base_sha": self.base,
                  "upstream_sha": "b" * 40, "version": self.version, "apks": records}
        (self.signed / "signing-verification.json").write_text(json.dumps(report))
        self.source = self.root / "source.tar.gz"
        self.source.write_bytes(b"complete source fixture")
        self.uploads, self.requests = {}, []
        self.latest_id = 7

    def request(self, path, method="GET", data=None, **kwargs):
        self.requests.append((path, method, data))
        if path.endswith("/git/ref/heads/main"):
            return {"object": {"sha": self.base}}
        if method == "GET" and "/git/commits/" in path:
            return {"tree": {"sha": "d" * 40}}
        if method == "POST" and "/git/" in path:
            return {"sha": "c" * 40}
        if path.endswith("/git/refs/heads/main") or "/releases/assets/" in path:
            return None
        if path.endswith("/releases/latest"):
            return {"id": self.latest_id, "assets": getattr(self, "public_assets", [])}
        if method == "PATCH" and data.get("draft") is False:
            # Latest must never point to a release with missing download assets.
            self.assertIn("app.apk", self.uploads)
            self.assertIn("SHA256SUMS", self.uploads)
            self.assertEqual(data, {"draft": False, "prerelease": False, "make_latest": "true"})
            return {"id": 7, "draft": False, "prerelease": False, "html_url": "https://example.invalid/release"}
        return {"id": 7, "draft": True, "prerelease": False, "body": release_android.MARKER, "assets": []}

    def publish(self, resume=False):
        if resume:
            self.plan.update(resume=True, files={})
        plan_path = self.root / "plan.json"
        plan_path.write_text(json.dumps(self.plan))
        current = self.version if resume else {"version_code": 8}
        draft = {"id": 7, "draft": True, "body": release_android.MARKER} if resume else None
        def read(path):
            return current if str(path) == "version.json" else json.loads(Path(path).read_text())
        with patch.object(release_android, "git", return_value=self.base), \
             patch.object(release_android, "read_json", side_effect=read), \
             patch.object(release_android, "api", side_effect=self.request), \
             patch.object(release_android, "find_release", return_value=draft), \
             patch.object(release_android, "upload_asset", side_effect=lambda release, path: self.uploads.update({path.name: path.read_bytes()})), \
             patch.dict(release_android.os.environ, {"GITHUB_RUN_ID": "456"}), contextlib.redirect_stdout(io.StringIO()):
            release_android.publish(plan_path, self.signed, self.source)

    def test_latest_download_is_the_verified_universal_apk(self):
        self.publish()
        universal = f"pikaraoke-tv-{self.version['version_name']}-universal.apk"
        self.assertEqual(self.uploads["app.apk"], self.uploads[universal])
        checksums = self.uploads["SHA256SUMS"].decode()
        self.assertIn(release_android.digest(self.signed / universal) + "  app.apk\n", checksums)
        create = next(data for path, method, data in self.requests if path.endswith("/releases") and method == "POST")
        self.assertTrue(create["draft"])
        self.assertFalse(create["prerelease"])
        self.assertTrue(self.requests[-1][0].endswith("/releases/latest"))

    def test_draft_retry_also_publishes_latest_universal(self):
        self.publish(resume=True)
        self.assertIn("app.apk", self.uploads)
        self.assertFalse(any(path.endswith("/releases") and method == "POST" for path, method, data in self.requests))

    def test_modified_apk_is_rejected_before_any_upload(self):
        (self.signed / f"pikaraoke-tv-{self.version['version_name']}-universal.apk").write_bytes(b"modified")
        with self.assertRaises(AssertionError):
            self.publish()
        self.assertEqual(self.uploads, {})
        self.assertEqual(self.requests, [])

    def test_wrong_latest_release_is_reported(self):
        self.latest_id = 8
        with self.assertRaisesRegex(AssertionError, "not GitHub's latest"):
            self.publish()

    def repair(self, change_assets=None):
        self.plan.update(publish=False, resume=False, files={}, repair_latest=True)
        plan_path = self.root / "repair-plan.json"
        plan_path.write_text(json.dumps(self.plan))
        assets = [{"name": name, "state": "uploaded", "size": len(data),
                   "digest": "sha256:" + release_android.hashlib.sha256(data).hexdigest()}
                  for name, data in self.uploads.items()]
        if change_assets:
            change_assets(assets)
        release = {"id": 7, "draft": False, "tag_name": self.version["release_tag"],
                   "body": release_android.MARKER, "assets": assets}
        self.public_assets = assets
        def read(path):
            return self.version if str(path) == "version.json" else json.loads(Path(path).read_text())
        with patch.object(release_android, "git", return_value=self.base), \
             patch.object(release_android, "read_json", side_effect=read), \
             patch.object(release_android, "api", side_effect=self.request), \
             patch.object(release_android, "find_release", return_value=release), \
             patch.object(release_android, "read_release_asset", side_effect=lambda tag, asset: self.uploads[asset["name"]]), \
             patch.object(release_android, "upload_asset") as upload, contextlib.redirect_stdout(io.StringIO()):
            release_android.repair_latest(plan_path)
            upload.assert_not_called()

    def test_latest_mismatch_then_rerun_repairs_without_replacing_public_assets(self):
        self.latest_id = 8
        with self.assertRaisesRegex(AssertionError, "not GitHub's latest"):
            self.publish()
        self.latest_id = 7
        self.requests.clear()
        self.repair()
        mutations = [(method, data) for path, method, data in self.requests if method != "GET"]
        self.assertEqual(mutations, [("PATCH", {"draft": False, "prerelease": False, "make_latest": "true"})])

    def test_repair_rejects_changed_or_missing_public_assets(self):
        self.publish()
        for change in (lambda assets: assets.pop(),
                       lambda assets: next(a for a in assets if a["name"] == "app.apk").update(digest="sha256:" + "0" * 64)):
            self.requests.clear()
            with self.assertRaises(AssertionError):
                self.repair(change)
            self.assertFalse(any(method != "GET" for path, method, data in self.requests))

    def test_metadata_download_checks_size_and_digest(self):
        data = b"release metadata"
        asset = {"name": "SHA256SUMS", "size": len(data),
                 "digest": "sha256:" + release_android.hashlib.sha256(data).hexdigest()}
        with patch.object(release_android.urllib.request, "urlopen", return_value=io.BytesIO(data)):
            self.assertEqual(release_android.read_release_asset(self.version["release_tag"], asset), data)
        with patch.object(release_android.urllib.request, "urlopen", return_value=io.BytesIO(b"altered metadata")):
            with self.assertRaises(AssertionError):
                release_android.read_release_asset(self.version["release_tag"], asset)


if __name__ == "__main__":
    unittest.main()
