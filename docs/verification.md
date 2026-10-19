# Release verification

Verified on 2026-10-19 using an ARM64 Android TV API 34 emulator on Apple silicon.
The app, Python service, media tools and browser all ran inside the APK.

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
32-bit ARM execution, x86-64 execution, and real phone/Wi-Fi connectivity have
not been physically verified. The external-client check used an ADB TCP tunnel.
Native libraries for all three advertised ABIs are present in their APKs.

Raw reports and the actual TV playback screenshot are retained locally under
`artifacts/verification/`. Release-specific persistence and online-download
results are added after the signed-APK check.

The upstream source is pinned to
`48c7122e16784417e43ae0c4f1d744ed2a0b6492` (PiKaraoke 1.23.0).
Android integration tests are in `app/src/androidTest/` and
`app/src/debug/python/device_checks.py`.
