# PiKaraoke TV

A standalone Android APK that hosts **PiKaraoke on the TV itself**. The APK
contains the Python server, the upstream web UI, an embedded GeckoView player,
yt-dlp, QuickJS, FFmpeg, and FFprobe. No computer, Termux, separate server, or
separately installed browser is required. Internet is needed for online search
and downloads; songs already saved on the TV play from local files.

## Install and use

Install a signed APK from this repository's Releases on Android 8.0 or later.
Choose `arm64-v8a` for a 64-bit ARM TV, `armeabi-v7a` for a 32-bit ARM TV, or the
universal APK if unsure. `x86_64` is also built for compatible devices/emulators.

1. Open **PiKaraoke TV** from the TV launcher.
2. Connect phones to the same local network and scan the on-screen QR code,
   or open `http://<TV's IP address>:8080` in a phone browser.
3. Search/download songs or browse the local library and queue them.
4. Press **Back**, **Menu**, or **OK** on the player to open room options.
   Media Play/Pause and Next control playback. The browser controller supports
   directional focus with the D-pad. Phones retain the original touch UI.

The first launch shows a random per-install **host password**. It is separate
from your Android/device password. Open room settings on a phone to change it.
The TV's Host password option shows the initial password, which becomes stale
if you change it. The app never contains a shared hardcoded password.
If you forget the host password, use **Host password → Set host password** on
the TV to replace it without deleting songs or settings.

The room continues serving phones and downloading while you visit another app.
Use **Stop room and exit** to stop the server and release its wake lock. Android
can still terminate the app under memory pressure or force-stop it; reopening
starts the room again. Keep the player open on the TV while singing.

## Song files

Downloads are real, persistent files, rather than a streaming cache, in:

```
/storage/emulated/0/Android/data/org.pikaraoke.tv/files/songs/
```

The app falls back to internal storage if external app storage is unavailable.
Files survive app updates and device restarts. Android removes app-specific
storage on uninstall: copy songs out before uninstalling or clearing app data.

**Import song files** uses Android's file picker and accepts multiple files.
For CDG pairs, select both the `.cdg` and companion audio file; ZIP/CDG/MCG,
video files, and the formats understood by upstream remain available.
The app provides a read-only **PiKaraoke songs** Android document-provider root
so a compatible file manager can copy/export downloaded files without root or
all-files access. **Open song files** opens that root when a document picker is
installed. Some TV firmware ships without one; use a compatible file manager
or `adb pull` for file transfer on those devices.

## Upstream and maintenance

`upstream/` is a **Git submodule of
[vicwomg/pikaraoke](https://github.com/vicwomg/pikaraoke)**, pinned to a commit.
It is not a reimplementation or a disconnected source copy. The APK packages
its actual server, templates, JavaScript, translations, queue, library database,
search/download handling, sessions/history/rankings, scoring, and settings.

`scripts/prepare_upstream.py` copies upstream into the build directory, compiles
translations, and makes a few checked substitutions: gevent -> standard threads,
the embedded WSGI server, and TV focus support. Each substitution verifies the
expected source text and fails on conflicts. The submodule remains pristine.
Android-specific paths, native executables, audio, network addresses, service
lifecycle, and browser hosting live in `app/src/main/`.

To update upstream deliberately:

```sh
git submodule update --init --recursive
git -C upstream fetch origin
git -C upstream checkout <reviewed-upstream-commit>
nix develop
export PIKARAOKE_BUILD_PYTHON="$(command -v python3)"
./gradlew assembleDebug connectedDebugAndroidTest
git add upstream
git commit -m "Update pinned PiKaraoke upstream"
```

Python runtime requirements and their transitive versions are pinned in
`app/requirements-android.txt` and `app/constraints-android.txt`. The downloader
zipapp is pinned by version and SHA-256 in `scripts/fetch_ytdlp.py`; it overrides
the older resource in the native runtime library. The upstream Update yt-dlp
action uses the Android library's updater; it does not try to install pip into
Android. Updating yt-dlp may be needed when YouTube changes its service.

## Platform adaptations

| Feature | Android implementation |
| --- | --- |
| Phone UI, queue, local library, sessions/history, rankings, score, language and settings | Actual upstream application |
| Local TV player, overlays, background music/video, subtitles | Upstream player in bundled GeckoView |
| Downloads and search | Packaged yt-dlp executable/Python runtime and QuickJS |
| Transcoding, HLS, CDG, pitch, normalization, A/V sync | Packaged FFmpeg/FFprobe; software H.264 encoding |
| Microphone passthrough | Android AudioRecord/AudioTrack; explicit runtime permission; supported input devices including USB |
| Microphone echo cancellation | Android effect when provided by the device; hardware dependent |
| Keep awake | Foreground service wake lock and player screen flag |
| File import/export | Android file picker and document provider |
| CPU/memory/disk info | Android memory and filesystem measurements; CPU accounting is reported unsupported |
| Raspberry Pi filesystem expansion / OS reboot / OS shutdown | Require OS privileges outside an ordinary Android APK; use Android's device controls |

Microphone hardware, latency, audio routing and supported codecs depend on the
TV. Software transcoding of high-resolution non-H.264 files can be expensive
on small TV sticks. Prefer H.264/AAC MP4 downloads for those devices. The package
has no root requirement and does not attempt to root or administer the TV.

## Build

```sh
git clone --recurse-submodules https://github.com/nabekhan/pikaraoke-android.git
cd pikaraoke-android
nix develop
export PIKARAOKE_BUILD_PYTHON="$(command -v python3)"
./gradlew assembleDebug
```

The pinned Nix flake supplies JDK 17, Gradle, Python with Babel, Android SDK,
FFmpeg and emulator tools. `nix build .#sdk` builds only the compilation SDK;
`nix build .#tv-emulator` supplies an ARM64 Android TV API 34 image on Apple
silicon. The alternate emulator package includes a phone API 35 image.

Without Nix, install JDK 17, Python 3.11 with Babel, Android SDK platform 37.2 and
build-tools 36.0.0, set `ANDROID_HOME`, and run the same Gradle wrapper commands.
Gradle downloads Maven/Python dependencies and the checksum-verified downloader
on the build machine. They are bundled into the resulting APK.

Release signing is opt-in through environment variables:

```
PIKARAOKE_KEYSTORE
PIKARAOKE_STORE_PASSWORD
PIKARAOKE_KEY_ALIAS
PIKARAOKE_KEY_PASSWORD
```

Keep the keystore and passwords outside the repository and preserve them for
updates. `./gradlew assembleRelease` produces ABI-specific and universal APKs.
Without signing variables, release APKs are unsigned and must be signed before
installation. Debug builds use the ordinary Android debug signing identity.

## Verification

`RoomIntegrationTest` launches the actual app and runs tests inside the Android
process. It checks guest/host authorization, upstream pages, FFmpeg features,
QuickJS, a download through the upstream download queue into a file, media
probing, actual browser playback position reports, pause/resume, real pitch and
normalization processing, and Android system statistics. Its generated test
video and source server run on the Android device. They are test fixtures, not
evidence that YouTube or physical microphones work. Test helpers are excluded
from release builds.

See `docs/verification.md` for the evidence and limitations of the release.

## Third-party components

The Android integration is licensed under GPL-3.0; see [LICENSE](LICENSE).
See [THIRD_PARTY.md](THIRD_PARTY.md) for dependency sources. Upstream and bundled
dependencies retain their own copyright notices and licenses. The APK includes
these notices under `assets/licenses/`.
