# Components and corresponding source

This Android integration is distributed under GPL-3.0; see `LICENSE`. Its source
and build instructions are at https://github.com/nabekhan/pikaraoke-android.
Clone with `--recurse-submodules` to obtain the exact upstream source dependency;
GitHub's automatic source ZIP does not include Git submodule contents.

This Android integration packages these independently maintained components.
Their source, notices, and license terms remain with their respective projects:

| Component | Version/source |
| --- | --- |
| PiKaraoke | Pinned `upstream/` submodule: https://github.com/nabekhan/pikaraoke, forked from https://github.com/vicwomg/pikaraoke |
| Chaquopy | 17.0.0, https://github.com/chaquo/chaquopy |
| CPython | 3.11 via Chaquopy and native downloader Python via youtubedl-android, https://github.com/python/cpython |
| GeckoView | 158.0.20261007201254, https://archive.mozilla.org/pub/firefox/releases/158.0/source/ and https://hg.mozilla.org/releases/mozilla-release/ |
| youtubedl-android + FFmpeg AAR | 0.18.1, https://github.com/yausername/youtubedl-android/tree/0.18.1; native build/source instructions: https://github.com/yausername/youtubedl-android/blob/master/BUILD_FFMPEG.md |
| yt-dlp | 2026.08.19 initial resource, https://github.com/yt-dlp/yt-dlp/tree/2026.08.19 |
| FFmpeg and native libraries including Rubber Band | Distributed through the above FFmpeg AAR; source/build instructions in its repository; https://ffmpeg.org/ and https://breakfastquay.com/rubberband/ |
| QuickJS | Distributed through youtubedl-android, https://bellard.org/quickjs/ |
| Flask and Python dependencies | Exact installed versions in `app/constraints-android.txt`, source URLs and licenses in the wheels' packaged `.dist-info` metadata |
| WebRTC Android SDK | `android-prefixed-stripped` 150.7871.01, https://github.com/webrtc-sdk/android; WebRTC BSD notices: https://github.com/webrtc-sdk/android/tree/main/Licenses |
| Bouncy Castle | 1.86, https://github.com/bcgit/bc-java; MIT license, https://www.bouncycastle.org/licence.html |

Phone audio uses JackTrip's documented DEFAULT packet layout (mono PCM16) over
an unordered, unreliable WebRTC data channel. The packet parser and bounded
receiver/mixer are in the PiKaraoke fork; this does not bundle the JackTrip app or
claim compatibility with its complete signaling protocol. Reference:
https://github.com/jacktrip/jacktrip/blob/v3.0.1/docs/Documentation/NetworkProtocol.md.
The interface follows Apple Music Sing's microphone layout using our own HTML,
CSS, and SVG icons; no Apple artwork or application code is included.

The PiKaraoke fork retains the original history and holds shared features and
receiver integrations. The Android build generates platform adaptations only
under `app/build/`. Packaging and TV controls are in this repository. GeckoView includes its own runtime `about:license` notices.
The launcher artwork is taken unchanged from upstream's `static/icons/logo.ico`
during the build.
