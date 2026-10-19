# Components and corresponding source

This Android integration is distributed under GPL-3.0; see `LICENSE`. Its source
and build instructions are at https://github.com/nabekhan/pikaraoke-android.
Clone with `--recurse-submodules` to obtain the exact upstream source dependency;
GitHub's automatic source ZIP does not include Git submodule contents.

This Android integration packages these independently maintained components.
Their source, notices, and license terms remain with their respective projects:

| Component | Version/source |
| --- | --- |
| PiKaraoke | Pinned `upstream/` submodule and its Git history: https://github.com/vicwomg/pikaraoke |
| Chaquopy | 17.0.0, https://github.com/chaquo/chaquopy |
| CPython | 3.11 via Chaquopy and native downloader Python via youtubedl-android, https://github.com/python/cpython |
| GeckoView | 158.0.20261007201254, https://archive.mozilla.org/pub/firefox/releases/158.0/source/ and https://hg.mozilla.org/releases/mozilla-release/ |
| youtubedl-android + FFmpeg AAR | 0.18.1, https://github.com/yausername/youtubedl-android/tree/0.18.1; native build/source instructions: https://github.com/yausername/youtubedl-android/blob/master/BUILD_FFMPEG.md |
| yt-dlp | 2026.08.19 initial resource, https://github.com/yt-dlp/yt-dlp/tree/2026.08.19 |
| FFmpeg and native libraries including Rubber Band | Distributed through the above FFmpeg AAR; source/build instructions in its repository; https://ffmpeg.org/ and https://breakfastquay.com/rubberband/ |
| QuickJS | Distributed through youtubedl-android, https://bellard.org/quickjs/ |
| Flask and Python dependencies | Exact installed versions in `app/constraints-android.txt`, source URLs and licenses in the wheels' packaged `.dist-info` metadata |

The original upstream tree is retained verbatim. The Android build generates
adapted source only under `app/build/`; all integration changes are in this
repository. GeckoView includes its own runtime `about:license` notices.
