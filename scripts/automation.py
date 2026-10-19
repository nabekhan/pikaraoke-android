#!/usr/bin/env python3
"""Plan upstream updates without running upstream code; apply data-only plans."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tomllib
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY = "nabekhan/pikaraoke-android"
UPSTREAM = "vicwomg/pikaraoke"
ALLOWED_FILES = frozenset({
    "version.json", "ytdlp.json",
    "app/requirements-android.txt", "app/constraints-android.txt",
})
REPLACED_DEPENDENCIES = frozenset({"gevent", "psutil", "sounddevice", "yt-dlp"})
SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
PIN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*(?:\[[A-Za-z0-9_,.-]+\])?==[A-Za-z0-9][A-Za-z0-9.!+_-]*\Z")


def api(path, method="GET", data=None, missing_ok=False):
    url = "https://api.github.com/repos/" + path
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"}
    if os.environ.get("GH_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
    request = urllib.request.Request(
        url, data=None if data is None else json.dumps(data).encode(),
        headers=headers, method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return None if response.status == 204 else json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404 and missing_ok:
            return None
        raise RuntimeError(f"GitHub API {method} failed with HTTP {error.code}") from None



def find_release(tag):
    # Drafts may not yet have a Git tag. The list endpoint also exposes these
    # to a writer, so retries must check it before creating another draft.
    release = api(REPOSITORY + "/releases/tags/" + tag, missing_ok=True)
    if release:
        return release
    for page in range(1, 1001):
        values = api(REPOSITORY + f"/releases?per_page=100&page={page}")
        matches = [item for item in values if item["tag_name"] == tag]
        assert len(matches) <= 1, "Ambiguous release tag"
        if matches:
            return matches[0]
        if len(values) < 100:
            return None
    raise RuntimeError("Release history is too large; review required")


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def read_json(path):
    return json.loads(Path(path).read_text())


def json_text(value):
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def validate_version(value):
    assert isinstance(value, dict)
    assert type(value["version_code"]) is int and 0 < value["version_code"] <= 2100000000
    assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,99}", value["version_name"])
    if value.get("automated"):
        assert value["release_tag"] == "v" + value["version_name"]


def validate_plan(plan, current_version=None):
    assert plan["schema"] == 1 and SHA.fullmatch(plan["base_sha"])
    assert SHA.fullmatch(plan["upstream_sha"])
    assert type(plan["publish"]) is bool and type(plan["resume"]) is bool
    assert isinstance(plan["files"], dict) and set(plan["files"]) <= ALLOWED_FILES
    for name, text in plan["files"].items():
        assert isinstance(text, str) and len(text.encode()) < 100000
        if name.endswith(".txt"):
            for line in text.splitlines():
                if line and not line.startswith("#") and line != "-c constraints-android.txt":
                    assert PIN.fullmatch(line), "Dependency updates must contain version pins only"
    version = plan["version"]
    validate_version(version)
    if plan["publish"]:
        assert version.get("automated") is True
        assert version["release_tag"] == plan["release_tag"]
        assert version["upstream_sha"] == plan["upstream_sha"]
        if current_version:
            expected = current_version["version_code"] + (0 if plan["resume"] else 1)
            assert version["version_code"] == expected, "Unexpected Android version counter"
        if not plan["resume"]:
            assert "version.json" in plan["files"]
        if "version.json" in plan["files"]:
            assert json.loads(plan["files"]["version.json"]) == version
    if "ytdlp.json" in plan["files"]:
        pin = json.loads(plan["files"]["ytdlp.json"])
        assert re.fullmatch(r"20\d{2}\.\d{2}\.\d{2}", pin["version"])
        assert DIGEST.fullmatch(pin["sha256"])


def checksum_for_zipapp(text):
    matches = [
        line.split()[0] for line in text.splitlines()
        if len(line.split()) == 2 and line.split()[1].lstrip("*") == "yt-dlp"
    ]
    assert len(matches) == 1 and DIGEST.fullmatch(matches[0]), "No unique yt-dlp checksum"
    return matches[0]


def resolve_requirements(pyproject):
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    from packaging.specifiers import SpecifierSet
    assert SpecifierSet(pyproject["project"].get("requires-python", ">=3.10")).contains("3.11")
    requested = []
    for text in pyproject["project"]["dependencies"]:
        requirement = Requirement(text)
        assert not requirement.url, "Upstream URL dependencies require review"
        if canonicalize_name(requirement.name) in REPLACED_DEPENDENCIES:
            continue
        if requirement.marker and not requirement.marker.evaluate():
            continue
        requested.append(str(requirement))
    requested.append("simple-websocket>=1.1,<2")
    with tempfile.TemporaryDirectory(prefix="pikaraoke-resolver-") as folder:
        folder = Path(folder)
        source = folder / "requirements.txt"
        source.write_text("\n".join(requested) + "\n")
        report = folder / "resolution.json"
        command = [
            sys.executable, "-m", "pip", "install", "--dry-run", "--ignore-installed",
            "--only-binary=:all:", "--disable-pip-version-check", "--report", str(report),
            "-r", str(source),
        ]
        # Keep working pins until upstream's requirements make them incompatible.
        old = Path("app/constraints-android.txt")
        result = subprocess.run(command + ["-c", str(old)], capture_output=True, text=True)
        if result.returncode:
            result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError("Python dependency resolution failed; no APK will be published")
        installed = read_json(report)["install"]
    versions = {
        canonicalize_name(item["metadata"]["name"]):
        (item["metadata"]["name"], item["metadata"]["version"])
        for item in installed
    }
    direct = []
    for text in requested:
        requirement = Requirement(text)
        name, version = versions[canonicalize_name(requirement.name)]
        extras = "[" + ",".join(sorted(requirement.extras)) + "]" if requirement.extras else ""
        direct.append(f"{name}{extras}=={version}")
    requirements = (
        "# Generated from upstream pyproject.toml; Android replaces gevent, psutil,\n"
        "# sounddevice and yt-dlp. The threaded server also needs simple-websocket.\n"
        "-c constraints-android.txt\n" + "\n".join(sorted(direct, key=str.lower)) + "\n"
    )
    constraints = (
        "# Compatible pins retained; re-resolved only when upstream requires it.\n" +
        "\n".join(f"{name}=={version}" for _, (name, version) in sorted(versions.items())) + "\n"
    )
    return requirements, constraints


def make_plan(force=False):
    current = read_json("version.json")
    validate_version(current)
    base = git("rev-parse", "HEAD")
    current_upstream = git("ls-tree", "HEAD", "upstream").split()[2]
    plan = {
        "schema": 1, "base_sha": base, "upstream_sha": current_upstream,
        "publish": False, "resume": False, "files": {}, "version": current,
    }
    if current.get("automated"):
        existing = find_release(current["release_tag"])
        if not existing or existing["draft"]:
            plan.update(publish=True, resume=True, release_tag=current["release_tag"])
            validate_plan(plan, current)
            return plan
        if current.get("automation_run_id") == os.environ.get("GITHUB_RUN_ID"):
            return plan  # A successful run was rerun; never publish it twice.
    upstream = api(UPSTREAM)
    branch = urllib.parse.quote(upstream["default_branch"], safe="")
    upstream_sha = api(UPSTREAM + "/commits/" + branch)["sha"]
    assert SHA.fullmatch(upstream_sha)
    # Refuse upstream branch rewrites/downgrades rather than silently following.
    if upstream_sha != current_upstream:
        comparison = api(UPSTREAM + "/compare/" + current_upstream + "..." + upstream_sha)
        assert comparison["status"] in ("ahead", "identical"), "Upstream history rewrote; review required"
    contents = api(UPSTREAM + "/contents/pyproject.toml?ref=" + upstream_sha)
    project = tomllib.loads(base64.b64decode(contents["content"]).decode())
    upstream_version = project["project"]["version"]
    assert re.fullmatch(r"\d+(?:\.\d+){1,3}(?:[A-Za-z0-9.+-]*)", upstream_version)
    requirements, constraints = resolve_requirements(project)
    proposed = {
        "app/requirements-android.txt": requirements,
        "app/constraints-android.txt": constraints,
    }
    latest = api("yt-dlp/yt-dlp/releases/latest")
    assert not latest["draft"] and not latest["prerelease"]
    yt_version = latest["tag_name"]
    assert re.fullmatch(r"20\d{2}\.\d{2}\.\d{2}", yt_version)
    # Download only the public checksum document; no token follows asset redirects.
    with urllib.request.urlopen(
        "https://github.com/yt-dlp/yt-dlp/releases/download/" + yt_version + "/SHA2-256SUMS",
        timeout=60,
    ) as response:
        checksum = checksum_for_zipapp(response.read().decode())
    old_yt = read_json("ytdlp.json")
    assert yt_version >= old_yt["version"], "Refusing a yt-dlp downgrade"
    proposed["ytdlp.json"] = json_text({"version": yt_version, "sha256": checksum})
    changes = {name: text for name, text in proposed.items() if Path(name).read_text() != text}
    if not force and upstream_sha == current_upstream and not changes:
        return plan
    code = current["version_code"] + 1
    version = {
        "version_code": code, "version_name": f"{upstream_version}-android.{code}",
        "automated": True, "upstream_sha": upstream_sha, "yt_dlp_version": yt_version,
        "automation_run_id": os.environ["GITHUB_RUN_ID"],
    }
    version["release_tag"] = "v" + version["version_name"]
    changes["version.json"] = json_text(version)
    plan.update(
        publish=True, files=changes, version=version, upstream_sha=upstream_sha,
        release_tag=version["release_tag"],
    )
    validate_plan(plan, current)
    return plan


def apply_plan(path):
    plan = read_json(path)
    assert git("rev-parse", "HEAD") == plan["base_sha"]
    validate_plan(plan, read_json("version.json"))
    for name, text in plan["files"].items():
        destination = Path(name)
        assert not destination.is_symlink()
        destination.write_text(text)
    subprocess.run(["git", "-C", "upstream", "fetch", "--depth=1", "origin", plan["upstream_sha"]], check=True)
    subprocess.run(["git", "-C", "upstream", "checkout", "--detach", plan["upstream_sha"]], check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["plan", "apply"])
    parser.add_argument("path")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.operation == "apply":
        apply_plan(args.path)
    else:
        plan = make_plan(args.force)
        Path(args.path).write_text(json_text(plan))
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as output:
                output.write("publish=" + str(plan["publish"]).lower() + "\n")
                output.write("base_sha=" + plan["base_sha"] + "\n")
        print(json.dumps({
            "publish": plan["publish"], "resume": plan["resume"],
            "upstream": plan["upstream_sha"], "version": plan["version"]["version_name"],
        }))


if __name__ == "__main__":
    main()
