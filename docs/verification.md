# Release verification

## Phone microphone prototype

- [Android TV API 36 test run](https://github.com/nabekhan/pikaraoke-android/actions/runs/39335177016): all three device tests passed.
- Four native WebRTC senders connected at once and sent PCM audio to the TV's AudioTrack mixer.
- A fifth sender was refused; leaving freed a slot.
- Per-install CA generation, certificate signatures, and IP address renewal passed.
- The actual Android HTTPS listener served the mic page and accepted four guest reservations using its trusted CA.
- HTTP mic mutations and requests from another origin were refused.
- The existing song download, processing, playback, authentication, and file-access test passed.
- Browser checks cover worklet framing, connection state, mute, stale-audio drops, and cleanup after interrupted startup.
- Physical phones, Wi-Fi audio, audible latency, and feedback still need testing.

## Original release

Verified on 2026-10-19 using an ARM64 Android TV API 34 emulator on Apple silicon.
The app, Python service, media tools and browser all ran inside the APK.
The same integration test also passed on an x86-64 Android TV API 36 emulator
in [GitHub Actions](https://github.com/nabekhan/pikaraoke-android/actions/runs/39246935553):
one test passed, none failed or skipped, in 89.10 seconds. Both build and
device-test jobs succeeded for release commit `9dfb741`.

| Check | Evidence |
| --- | --- |
| Android build | Local debug/release builds succeeded; release lint passed; GitHub Actions also built the project |
| Actual upstream pages | Home, player, library, queue, search, info, settings, history, sessions and rankings returned HTTP 200 on Android |
| Authentication | Anonymous host control refused with 403; password login and authenticated actions succeeded |
| Download to file | The upstream download queue downloaded a generated HTTP video into the song directory; FFprobe measured its 24-second duration |
| Actual TV playback | The embedded GeckoView player reported playback position 2.793791 seconds through the original player handshake; HLS init/segments were served on Android |
| Processing | Native FFmpeg exposed H.264/AAC, Rubber Band and loudness filters; real pitch/normalization processing succeeded |
| External remote client | A separate host-side HTTP/Socket.IO client queued a song, changed its key to +2 during playback, and set volume to 0.4 |
| File access | Android document-provider root/query/read succeeded; traversal outside the song directory was refused |
| Online search | A YouTube search through the Android server returned real results |
| Live YouTube download | The signed release downloaded `jNQXAC9IVRw` through the original queue, saved an MP4, and played that saved file in the final signed APK (reported position 2.715833 seconds) |
| Signed APK lifecycle | Password login, actual playback, remote Quit followed by reopening, and library persistence succeeded in the signed release |
| APK update | Installing the final signed APK over the candidate preserved authentication, the library, and the exact SHA-256 of a saved song |
| Runtime | PiKaraoke 1.23.0; FFmpeg 7.1.1; yt-dlp 2026.08.19; bundled QuickJS executed JavaScript |
| APK signature | RSA 3072-bit distribution key; APK Signature Scheme v2 verification succeeded |

`RoomIntegrationTest` completed with `OK (1 test)` in 62.614 seconds. Its direct
HTTP fixture uses `-f best`, because a direct media URL has no YouTube height
metadata for the upstream resolution selector. This verifies the real download
queue, filesystem, transcoding and browser path; it does not substitute for a
live YouTube download.

The first emulator software graphics backend stalled inside Android's renderer.
Switching to host graphics resolved the emulator issue. Interrupted emulator
storage also exposed truncated runtime caches; startup now validates and repairs
the packaged Python/native caches. The Android server uses port **8080**, avoiding
the emulator/Android-debugging conflict on upstream's default port 5555.

Physical TV hardware, USB microphone routing, audible latency/echo cancellation,
and real phone/Wi-Fi connectivity have not been physically verified. 32-bit ARM
execution has not been tested. The external-client check used an ADB TCP tunnel.
Native libraries for all three advertised ABIs are present in their APKs.
All four release APKs passed APK v2 signature verification with certificate
SHA-256 `feded228e772fc3cf25cabfbaf0daf587d996fd8672da4bdc61142c592368104`.

GitHub's optional x86-64 device-test job initially could not boot its emulator
because the hosted runner ran out of disk space. The workflow now frees unused
hosted tools and bounds the AVD partition size. The rerun passed the actual
Android integration test. The earlier boot failure occurred before app installation.

Raw reports and TV playback screenshots are preserved in the release attachment
`pikaraoke-tv-0.1.0-verification.tar.gz`. `release-result.json` records the
signed-APK checks.

The upstream source is pinned to
`48c7122e16784417e43ae0c4f1d744ed2a0b6492` (PiKaraoke 1.23.0).
Android integration tests are in `app/src/androidTest/` and
`app/src/debug/python/device_checks.py`.
