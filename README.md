# PiKaraoke TV

- [PiKaraoke](https://github.com/vicwomg/pikaraoke) for Android TV.
- Server and player run on the TV.
- Phones connect through a browser on the same network.
- Downloads stay on the TV and can play offline.

## Install

- Requires Android 8.0 or later.
- Download an APK from [Releases](https://github.com/nabekhan/pikaraoke-android/releases).
- Use `arm64-v8a` for 64-bit ARM, `armeabi-v7a` for 32-bit ARM, or `universal` if unsure.
- `x86_64` is available for compatible devices and emulators.
- Sideload the APK and open **PiKaraoke TV**.
- Scan the QR code on a phone, or open `http://<TV-IP>:8080`.

## Use

- Use your phone to search, download, queue songs, and change settings.
- On the TV, press **Back**, **Menu**, or **OK** for room options.
- Media **Play/Pause** and **Next** control playback.
- The host password appears on first launch. Change it in room settings.
- Reset a forgotten password on the TV: **Host password → Set host password**.
- **Stop room and exit** shuts down the server.

## Files

- Songs are saved in `/storage/emulated/0/Android/data/org.pikaraoke.tv/files/songs/`.
- **Import song files** opens the file picker. Select both files for CDG/audio pairs.
- **Open song files** lets a compatible file manager copy songs out.
- Some TVs need a file manager installed for import/export.
- Songs and settings survive app updates.
- Back up songs before uninstalling or clearing app data.

## Updates

- GitHub checks PiKaraoke and yt-dlp weekly.
- Updates are built, tested on an Android TV emulator, signed, and published to Releases.
- Install the new APK on the TV to update.
- For an immediate check, open [Actions](https://github.com/nabekhan/pikaraoke-android/actions/workflows/update-release.yml) and select **Run workflow**.
- Upstream code is kept as a Git submodule in `upstream/`.
- [Workflow details](docs/automation.md).

## Build

- With Nix:

```sh
git clone --recurse-submodules https://github.com/nabekhan/pikaraoke-android.git
cd pikaraoke-android
nix develop
export PIKARAOKE_BUILD_PYTHON="$(command -v python3)"
./gradlew assembleDebug
```

- Without Nix: JDK 17, Python 3.11 with Babel, Android SDK 37.2, build-tools 36.0.0, and `ANDROID_HOME`.
- `./gradlew assembleRelease` builds unsigned release APKs unless signing is configured.
- Local signing uses `PIKARAOKE_KEYSTORE`, `PIKARAOKE_STORE_PASSWORD`, `PIKARAOKE_KEY_ALIAS`, and `PIKARAOKE_KEY_PASSWORD`.

## Notes

- Optional TV/USB microphone passthrough is untested on physical hardware.
- Phones currently act as remotes, not microphones.
- Raspberry Pi OS controls such as reboot and filesystem expansion are unavailable.
- [Test results and limitations](docs/verification.md).
- [GPL-3.0 license](LICENSE) · [Third-party components](THIRD_PARTY.md).
