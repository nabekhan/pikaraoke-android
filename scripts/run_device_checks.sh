#!/usr/bin/env bash
set -uo pipefail
./gradlew "$@" connectedDebugAndroidTest --console=plain
result=$?
mkdir -p tv-screenshots
for screen in room playing; do
  adb pull "/data/local/tmp/pikaraoke-tv-$screen.png" "tv-screenshots/tv-$screen.png" || true
done
adb exec-out screencap -p > tv-screenshots/tv-final.png || true
adb logcat -d -v brief PiKaraoke:V PiKaraokePhoneMic:V python.stderr:V python.stdout:V AndroidRuntime:E '*:S' \
  | sed -E 's@(/api/phone-mics/)[0-9a-f-]{36}@\1<session>@g' > tv-screenshots/runtime.txt || true
exit "$result"
