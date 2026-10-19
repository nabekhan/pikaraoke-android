#!/usr/bin/env bash
set -uo pipefail
./gradlew connectedDebugAndroidTest --console=plain
result=$?
mkdir -p tv-screenshots
adb pull /sdcard/Android/data/org.pikaraoke.tv/files/screenshots ./tv-screenshots/ || true
adb exec-out screencap -p > tv-screenshots/tv-final.png || true
adb logcat -d -v brief PiKaraoke:V PiKaraokePhoneMic:V python.stderr:V python.stdout:V AndroidRuntime:E '*:S' \
  | sed -E 's@(/api/phone-mics/)[0-9a-f-]{36}@\1<session>@g' > tv-screenshots/runtime.txt || true
exit "$result"
