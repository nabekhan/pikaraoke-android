# PiKaraoke TV

- [PiKaraoke](https://github.com/vicwomg/pikaraoke) for Android TV.
- Server and player run on the TV.
- Phones connect through a browser on the same network.
- Downloads stay on the TV and can play offline.

## Install

- Requires Android 8.0 or later.
- Download the [latest universal APK](https://github.com/nabekhan/pikaraoke-android/releases/latest/download/app.apk), or choose a smaller APK from [Releases](https://github.com/nabekhan/pikaraoke-android/releases).
- In Downloader, enter **5094851** or [aftv.news/5094851](https://aftv.news/5094851).
- Use `arm64-v8a` for 64-bit ARM, `armeabi-v7a` for 32-bit ARM, or `universal` if unsure.
- `x86_64` is available for compatible devices and emulators.
- Sideload the APK and open **PiKaraoke TV**.
- Scan the QR code on a phone, or open `http://<TV-IP>:8080`.

## Use

- Use your phone to search, download, queue songs, and change settings.
- On the TV, press **Back**, **Menu**, or **OK** for room options.
- Media **Play/Pause** and **Next** control playback.
- New installs have no admin password. Admin access opens automatically while the password is blank.
- Set or clear the password in room settings. Updates keep any password already set.
- Reset a forgotten password on the TV: **Host password**.
- **Stop room and exit** shuts down the server.

## Files

- Songs are saved in `/storage/emulated/0/Android/data/org.pikaraoke.tv/files/songs/`.
- **Import song files** opens the file picker. Select both files for CDG/audio pairs.
- **Open song files** lets a compatible file manager copy songs out.
- Some TVs need a file manager installed for import/export.
- Songs and settings survive app updates.
- Back up songs before uninstalling or clearing app data.
- Set a folder limit in **Settings → Song storage**, in MB or GB. `0` turns it off.
- On next app start, oldest songs are deleted until the folder is under the limit. File dates determine age; paired files are removed together.
- Incomplete downloads and unrelated files are kept, so these can prevent reaching the limit.

## Phone microphones (prototype)

- Two phone mics by default. Choose 1–4 in **Settings → Playback and audio → Phone mic limit**.
- Open the microphone icon in the phone web interface.
- Uses the name you already entered in PiKaraoke.
- Starting the mic opens HTTPS, with brief certificate install steps if needed.
- On iPhone, also enable full trust under Settings → General → About → Certificate Trust Settings.
- Phones need the same local network as the TV. Audio stays on that network.
- Slide the mic up to connect, down to disconnect. Taps do not switch it on or off.
- Tap the volume or reverb icon to adjust it.
- Choose **Volume → Phone** to play the mic through the phone's speaker instead of the TV.
- Phone output starts at 15%. Raise it gradually; lower it if you hear feedback.
- Phone output stays on the phone and does not use a TV mic slot.
- Android enters full screen when the mic starts. Use the full-screen icon to switch back.
- Tap the lock to block controls. Hold it for 1.4 seconds to unlock.
- The top-right button returns to PiKaraoke and disconnects the mic.
- Disconnect to free a slot. Lost connections expire automatically.
- Each TV generates its own certificates. Private keys stay in app storage.
- Latency depends on the phone, Wi-Fi, and TV.
- [Latency tests and tuning](https://github.com/nabekhan/pikaraoke/blob/master/docs/PHONE_MIC_LATENCY.md).

## Updates

- GitHub checks the [PiKaraoke fork](https://github.com/nabekhan/pikaraoke) and yt-dlp weekly.
- The fork keeps the microphone UI, certificates, audio receiver, and storage limit. It merges original PiKaraoke updates weekly.
- Updates are built, tested on an Android TV emulator, signed, and published to Releases.
- Install the new APK on the TV to update.
- For an immediate check, open [Actions](https://github.com/nabekhan/pikaraoke-android/actions/workflows/update-release.yml) and select **Run workflow**.
- The fork is pinned as a Git submodule in `upstream/`. Android packaging and TV controls stay here.
- [Workflow details](docs/automation.md).

## Build

- Install JDK 17, Python 3.11, and the Android SDK (platform 37.2, build-tools 36.0.0, NDK 28.2.13676358, CMake 3.22.1).
- Set `ANDROID_HOME` to the SDK directory. Android Studio's SDK Manager can install the required SDK packages.

```sh
git clone --recurse-submodules https://github.com/nabekhan/pikaraoke-android.git
cd pikaraoke-android
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install Babel==2.17.0
export PIKARAOKE_BUILD_PYTHON="$(command -v python3)"
./gradlew assembleDebug
```

- On Windows, activate the virtual environment and set environment variables using your shell's equivalent commands.
- `./gradlew assembleRelease` builds unsigned release APKs unless signing is configured.
- Local signing uses `PIKARAOKE_KEYSTORE`, `PIKARAOKE_STORE_PASSWORD`, `PIKARAOKE_KEY_ALIAS`, and `PIKARAOKE_KEY_PASSWORD`.
- Nix users can use the optional `nix develop` environment instead of installing build tools manually.

## Notes

- Optional TV/USB microphone passthrough is untested on physical hardware.
- Raspberry Pi OS controls such as reboot and filesystem expansion are unavailable.
- [Test results and limitations](docs/verification.md).
- [GPL-3.0 license](LICENSE) · [Third-party components](THIRD_PARTY.md).
