#!/usr/bin/env python3
"""Sign prebuilt APKs in isolation, then publish on a separate clean runner."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
import zipfile

from automation import ALLOWED_FILES, REPOSITORY, api, find_release, git, json_text, read_json, validate_plan

CERTIFICATE = "feded228e772fc3cf25cabfbaf0daf587d996fd8672da4bdc61142c592368104"
ABIS = ("arm64-v8a", "armeabi-v7a", "x86_64", "universal")
MARKER = "<!-- managed-by: pikaraoke-android/update-release -->"


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def tool(name):
    return str(Path(os.environ["ANDROID_HOME"]) / "build-tools/36.0.0" / name)


def run(*command):
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return result.stdout


def validate_apk(path, version, abi):
    text = run(tool("aapt2"), "dump", "badging", str(path))
    package = re.search(r"^package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'", text)
    assert package and package.group(1) == "org.pikaraoke.tv"
    assert int(package.group(2)) == version["version_code"]
    assert package.group(3) == version["version_name"]
    assert "application-debuggable" not in text
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        present = sorted(n.split("/")[1] for n in names if n.endswith("/libxul.so"))
        assert present == (sorted(ABIS[:-1]) if abi == "universal" else [abi])
        assert "assets/licenses/LICENSE" in names


def sign(plan_path, source, destination):
    plan = read_json(plan_path)
    validate_plan(plan, read_json("version.json"))
    assert git("rev-parse", "HEAD") == plan["base_sha"]
    source, destination = Path(source), Path(destination)
    destination.mkdir()
    # Only this step receives secrets. No Gradle, pip, or upstream code runs.
    with tempfile.TemporaryDirectory(prefix="pikaraoke-signing-", dir=os.environ["RUNNER_TEMP"]) as private:
        keystore = Path(private) / "release.p12"
        keystore.write_bytes(base64.b64decode(os.environ["PIKARAOKE_KEYSTORE_B64"], validate=True))
        keystore.chmod(0o600)
        records = []
        for abi in ABIS:
            unsigned = source / f"app-{abi}-release-unsigned.apk"
            assert unsigned.is_file() and not unsigned.is_symlink()
            validate_apk(unsigned, plan["version"], abi)
            aligned = Path(private) / f"{abi}.apk"
            subprocess.run([tool("zipalign"), "-f", "4", str(unsigned), str(aligned)], check=True)
            final = destination / f"pikaraoke-tv-{plan['version']['version_name']}-{abi}.apk"
            run(
                tool("apksigner"), "sign", "--ks", str(keystore), "--ks-key-alias", "pikaraoke",
                "--ks-pass", "env:PIKARAOKE_STORE_PASSWORD",
                "--key-pass", "env:PIKARAOKE_KEY_PASSWORD",
                "--v1-signing-enabled", "false", "--v2-signing-enabled", "true",
                "--v3-signing-enabled", "false", "--v4-signing-enabled", "false",
                "--out", str(final), str(aligned),
            )
            verification = run(tool("apksigner"), "verify", "--verbose", "--print-certs", str(final))
            match = re.search(r"Signer #1 certificate SHA-256 digest: ([0-9a-f]+)", verification)
            assert match and match.group(1) == CERTIFICATE, "Wrong distribution key"
            assert "Verified using v2 scheme (APK Signature Scheme v2): true" in verification
            validate_apk(final, plan["version"], abi)
            records.append({"name": final.name, "sha256": digest(final), "bytes": final.stat().st_size})
        (destination / "signing-verification.json").write_text(json_text({
            "certificate_sha256": CERTIFICATE, "version": plan["version"], "apks": records,
            "upstream_sha": plan["upstream_sha"], "base_sha": plan["base_sha"],
        }))


def upload_asset(release, path):
    data = path.read_bytes()
    url = release["upload_url"].split("{", 1)[0] + "?" + urllib.parse.urlencode({"name": path.name})
    request = urllib.request.Request(url, data=data, method="POST", headers={
        "Authorization": "Bearer " + os.environ["GH_TOKEN"],
        "Content-Type": "application/octet-stream", "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(request, timeout=900) as response:
        uploaded = json.load(response)
    assert uploaded["size"] == len(data)
    assert uploaded["digest"] == "sha256:" + hashlib.sha256(data).hexdigest()


def read_release_asset(tag, asset):
    # Public release metadata only; never send a repository token to redirects.
    url = f"https://github.com/{REPOSITORY}/releases/download/" + "/".join(
        urllib.parse.quote(value, safe="") for value in (tag, asset["name"])
    )
    assert 0 < asset["size"] <= 1000000, "Unexpected metadata size"
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(1000001)
    assert len(data) == asset["size"]
    assert asset["digest"] == "sha256:" + hashlib.sha256(data).hexdigest()
    return data


def repair_latest(plan_path):
    plan = read_json(plan_path)
    assert git("rev-parse", "HEAD") == plan["base_sha"]
    validate_plan(plan, read_json("version.json"))
    assert plan.get("repair_latest")
    tag = plan["release_tag"]
    release = find_release(tag)
    assert release and not release["draft"] and MARKER in (release["body"] or "")
    assert release["tag_name"] == tag
    names = {f"pikaraoke-tv-{plan['version']['version_name']}-{abi}.apk" for abi in ABIS}
    expected = names | {"app.apk", "SHA256SUMS", "signing-verification.json",
                        "update-plan.json", "source-with-upstream.tar.gz"}
    assets = {asset["name"]: asset for asset in release["assets"]}
    assert len(assets) == len(release["assets"]) and set(assets) == expected
    for asset in assets.values():
        assert asset["state"] == "uploaded" and asset["size"] > 0
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", asset["digest"])
    checksums = {}
    for line in read_release_asset(tag, assets["SHA256SUMS"]).decode().splitlines():
        checksum, name = line.split("  ")
        assert name not in checksums and re.fullmatch(r"[0-9a-f]{64}", checksum)
        checksums[name] = checksum
    assert set(checksums) == expected - {"SHA256SUMS"}
    for name, checksum in checksums.items():
        assert assets[name]["digest"] == "sha256:" + checksum
    report = json.loads(read_release_asset(tag, assets["signing-verification.json"]))
    assert report["certificate_sha256"] == CERTIFICATE
    assert report["version"] == plan["version"] and report["upstream_sha"] == plan["upstream_sha"]
    tagged = api(REPOSITORY + "/commits/" + urllib.parse.quote(tag, safe=""))
    # Initial signing uses the version commit's parent; interrupted-publication
    # rebuilds sign from the already-committed version itself.
    assert len(tagged["parents"]) == 1
    assert report["base_sha"] in (tagged["sha"], tagged["parents"][0]["sha"])
    contents = api(REPOSITORY + "/contents/version.json?ref=" + tagged["sha"])
    assert json.loads(base64.b64decode(contents["content"])) == plan["version"]
    assert len(report["apks"]) == len(names) and {r["name"] for r in report["apks"]} == names
    for record in report["apks"]:
        asset = assets[record["name"]]
        assert asset["digest"] == "sha256:" + record["sha256"] and asset["size"] == record["bytes"]
    universal = assets[f"pikaraoke-tv-{plan['version']['version_name']}-universal.apk"]
    assert assets["app.apk"]["digest"] == universal["digest"]
    assert assets["app.apk"]["size"] == universal["size"]
    assert api(REPOSITORY + "/git/ref/heads/main")["object"]["sha"] == plan["base_sha"]
    published = api(REPOSITORY + "/releases/" + str(release["id"]), "PATCH", {
        "draft": False, "prerelease": False, "make_latest": "true",
    })
    assert not published["draft"] and not published["prerelease"]
    latest = api(REPOSITORY + "/releases/latest")
    assert latest["id"] == release["id"]
    assert {a["name"]: (a["size"], a["digest"], a["state"]) for a in latest["assets"]} == {
        name: (a["size"], a["digest"], a["state"]) for name, a in assets.items()
    }, "Release assets changed during repair"
    print(published["html_url"])


def publish(plan_path, signed, archive):
    plan = read_json(plan_path)
    assert git("rev-parse", "HEAD") == plan["base_sha"]
    validate_plan(plan, read_json("version.json"))
    assert plan["publish"]
    signed = Path(signed)
    report = read_json(signed / "signing-verification.json")
    assert report["certificate_sha256"] == CERTIFICATE
    assert report["version"] == plan["version"] and report["base_sha"] == plan["base_sha"]
    assert report["upstream_sha"] == plan["upstream_sha"]
    expected_names = {f"pikaraoke-tv-{plan['version']['version_name']}-{abi}.apk" for abi in ABIS}
    assert {r["name"] for r in report["apks"]} == expected_names
    assert {p.name for p in signed.iterdir()} == expected_names | {"signing-verification.json"}
    for record in report["apks"]:
        path = signed / record["name"]
        assert path.is_file() and not path.is_symlink()
        assert digest(path) == record["sha256"] and path.stat().st_size == record["bytes"]
    universal_name = f"pikaraoke-tv-{plan['version']['version_name']}-universal.apk"
    universal_record = next(record for record in report["apks"] if record["name"] == universal_name)
    # The stable download is a copy of the verified, signed universal APK.
    # Keep it inside the draft until every asset has passed upload verification.
    shutil.copyfile(signed / universal_name, signed / "app.apk")
    assert digest(signed / "app.apk") == universal_record["sha256"]
    source = Path(archive)
    assert source.is_file() and not source.is_symlink()
    shutil.copyfile(source, signed / "source-with-upstream.tar.gz")
    (signed / "update-plan.json").write_text(json_text(plan))
    (signed / "SHA256SUMS").write_text("".join(
        f"{digest(p)}  {p.name}\n" for p in sorted(signed.iterdir()) if p.name != "SHA256SUMS"
    ))
    current = api(REPOSITORY + "/git/ref/heads/main")["object"]["sha"]
    assert current == plan["base_sha"], "Main changed during testing; rerun against its new head"
    commit_sha = current
    if not plan["resume"]:
        parent = api(REPOSITORY + "/git/commits/" + current)
        entries = [{"path": "upstream", "mode": "160000", "type": "commit", "sha": plan["upstream_sha"]}]
        for name, text in plan["files"].items():
            assert name in ALLOWED_FILES
            blob = api(REPOSITORY + "/git/blobs", "POST", {
                "content": base64.b64encode(text.encode()).decode(), "encoding": "base64",
            })
            entries.append({"path": name, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        tree = api(REPOSITORY + "/git/trees", "POST", {"base_tree": parent["tree"]["sha"], "tree": entries})
        commit_sha = api(REPOSITORY + "/git/commits", "POST", {
            "message": "Update tested Android release " + plan["version"]["version_name"],
            "tree": tree["sha"], "parents": [current],
            "author": {"name": "github-actions[bot]", "email": "41898282+github-actions[bot]@users.noreply.github.com"},
        })["sha"]
    tag = plan["release_tag"]
    body = (
        MARKER + "\n\nStandalone PiKaraoke TV update built and tested automatically.\n\n"
        f"PiKaraoke source: {plan['upstream_sha']}\n\n"
        f"Android version: {plan['version']['version_name']} "
        f"(code {plan['version']['version_code']}).\n\n"
        f"Universal APK: https://github.com/{REPOSITORY}/releases/latest/download/app.apk\n\n"
        "The Android TV integration test and release lint passed before signing. "
        "All APKs use the original distribution certificate. Downloads and settings survive updates.\n\n"
        "Choose arm64-v8a for 64-bit ARM, armeabi-v7a for 32-bit ARM, or universal if unsure. "
        "Phones join through the TV QR code. Install the APK to update; TV installation is manual.\n\n"
        "Physical TV/microphone routing remains hardware dependent. "
        "SHA256SUMS, signing verification, the exact update plan, and complete source are attached.\n\n"
        f"Workflow: https://github.com/{REPOSITORY}/actions/runs/{os.environ['GITHUB_RUN_ID']}\n"
    )
    release = find_release(tag)
    if release:
        assert release["draft"] and MARKER in release["body"], "Refusing to overwrite another release"
        release = api(REPOSITORY + "/releases/" + str(release["id"]), "PATCH", {
            "target_commitish": commit_sha, "body": body, "name": "PiKaraoke TV " + plan["version"]["version_name"],
        })
        for asset in release["assets"]:
            api(REPOSITORY + "/releases/assets/" + str(asset["id"]), "DELETE")
    else:
        release = api(REPOSITORY + "/releases", "POST", {
            "tag_name": tag, "target_commitish": commit_sha,
            "name": "PiKaraoke TV " + plan["version"]["version_name"],
            "body": body, "draft": True, "prerelease": False,
        })
    for path in sorted(signed.iterdir()):
        upload_asset(release, path)
    # Merge the tested data-only update after every release asset is verified.
    if not plan["resume"]:
        api(REPOSITORY + "/git/refs/heads/main", "PATCH", {"sha": commit_sha, "force": False})
    published = api(REPOSITORY + "/releases/" + str(release["id"]), "PATCH", {
        "draft": False, "prerelease": False, "make_latest": "true",
    })
    assert not published["draft"] and not published["prerelease"]
    latest = api(REPOSITORY + "/releases/latest")
    assert latest["id"] == published["id"], "Published release is not GitHub's latest release"
    print(published["html_url"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["sign", "publish", "repair-latest"])
    parser.add_argument("plan")
    parser.add_argument("source", nargs="?")
    parser.add_argument("destination", nargs="?")
    args = parser.parse_args()
    if args.operation == "repair-latest":
        assert args.source is None and args.destination is None
        repair_latest(args.plan)
    elif args.operation == "sign":
        assert args.source and args.destination
        sign(args.plan, args.source, args.destination)
    else:
        assert args.source and args.destination
        publish(args.plan, args.source, args.destination)


if __name__ == "__main__":
    main()
