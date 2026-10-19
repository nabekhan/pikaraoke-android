# Automatic Android releases

[Update and release Android](../.github/workflows/update-release.yml) runs every
Monday at 08:23 UTC and can be started from GitHub Actions at any time. Changes
to the Android application, build scripts, tests, or update pins on main also
request a new release. All tools and emulators run on disposable GitHub runners;
a local Android SDK or running computer is unnecessary.

The updater follows the default branch of vicwomg/pikaraoke, retaining an exact
submodule commit. It checks the latest stable yt-dlp release and records the
official zipapp SHA-256 in ytdlp.json. Python dependencies come from upstream's
pyproject.toml, with the Android replacements excluded and simple-websocket
added. Existing compatible dependency pins are retained; the resolver changes
them only if upstream makes those pins incompatible. Resolution permits wheels
only and does not execute upstream packaging scripts.

Gradle, Android runtime, and GitHub Actions upgrades remain Dependabot pull
requests for review. The updater does not automatically rewrite Android adapters
or merge those pull requests. After a reviewed application or build change lands
on main, the release workflow tests and publishes the resulting app.

## Publication gates

1. A read-only job creates an immutable update plan. It permits changes only to
   the upstream gitlink, version.json, ytdlp.json, and the two Python pin files.
   Tests reject workflow changes, traversal paths, unpinned dependencies, and
   invalid or repeated version codes.
2. A separate read-only job applies the plan, builds unsigned release APKs, runs
   Android lint, and runs RoomIntegrationTest on an Android TV API 36 x86_64
   emulator. The complete source archive is uploaded before any build code runs.
   The test exercises the actual server, authorization, download queue,
   file storage, FFmpeg processing, and browser playback.
3. A fresh signing job receives the distribution key through the android-release
   environment, whose deployment branch policy allows main only. This job runs
   no Gradle, pip, or upstream code. It validates package name, version, ABI,
   license inclusion, and non-debuggable status, signs all four APKs, and verifies
   the original certificate and APK Signature Scheme v2.
4. Another fresh job has repository write permission but no signing secrets. It
   verifies every signed asset hash, uploads a managed draft release, verifies
   GitHub's upload digests, commits the tested data-only plan with a fast-forward
   main update, and publishes the release. If main moved during testing, it aborts.

Builds and emulator tests never receive signing secrets or repository write
permission. Third-party actions are pinned to full commit IDs. The signing
certificate SHA-256 is
feded228e772fc3cf25cabfbaf0daf587d996fd8672da4bdc61142c592368104.

## Versions and recovery

version.json holds the Android version counter. Automated releases increment it
and use names such as 1.23.0-android.2, where the first part is the PiKaraoke
version and the last number is the Android version code. The distribution key
remains the same as v0.1.0, allowing an in-place update that retains songs and
settings. Releases remain marked as prereleases because physical TV and
microphone compatibility depends on hardware.

When upstream and pins have not changed, scheduled and ordinary manual checks
stop without building or publishing. Select force_release when dispatching the
workflow to rebuild unchanged dependencies with a new Android version.

If testing fails, neither the main pin state nor the release changes. After a
failure during publication, rerun the workflow: a managed draft can be replaced,
and an already-committed version with an unpublished release resumes at that
version rather than allocating another one. A rerun of an already successful
workflow does not publish it twice. A main-branch race requires a fresh run.

Each release includes all four APKs, SHA256SUMS, signing-verification.json,
update-plan.json, and a complete source archive containing the exact upstream
source. Test reports are retained as workflow artifacts for seven days.
Installing an updated APK on the TV is manual; this workflow does not silently
install software on devices.

## Signing configuration

The android-release GitHub environment needs PIKARAOKE_KEYSTORE_B64,
PIKARAOKE_STORE_PASSWORD, and PIKARAOKE_KEY_PASSWORD. The keystore alias is
pikaraoke. These environment secrets are available only to the isolated signing
step. Keep the original key backup outside Git and preserve its password for
future updates. A different key cannot update an existing installation.
