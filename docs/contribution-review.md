# Upstream review

- Reviewed 24 fork commits, 52 Android commits, and 12 upstream commits since the original Android pin.
- Upstream baseline: [`4e52565`](https://github.com/vicwomg/pikaraoke/commit/4e525655fe0a633e380f6c3ed8beaa4b295cfb20).
- Android now depends directly on `vicwomg/pikaraoke`. The separate `nabekhan/pikaraoke` fork is no longer needed.
- Android main history and release tags are retained. Older releases include a complete source archive.

## Changes kept in Android

| Change | Location |
| --- | --- |
| APK packaging, embedded server, TV controls and startup | `app/src/main/java/`, `app/src/main/python/` |
| Phone mic UI, API and preferences | `app/src/main/phone-microphones/` |
| Certificates, receiver and native audio output | `app/src/main/java/`, `app/src/main/c/`, `app/src/main/python/` |
| Song storage limit and startup cleanup | `app/src/main/song-storage/` |
| Player source teardown and stale-event guards | `app/src/main/android-tv/` |

- `scripts/prepare_upstream.py` applies these additions to a build copy. The upstream submodule stays unchanged.
- Storage keeps its path checks, paired-file handling and recovery journal.
- The playback workaround was investigated on Android. We have no stock PiKaraoke reproduction, so it is not presented as an upstream fix.
- The phone-speaker experiment is removed. Current mic defaults remain two connections and 30% volume.
- [Phone mic branch](https://github.com/nabekhan/pikaraoke-android/tree/feature/phone-microphones) remains available; main includes it.

## Upstream overlap

| Upstream change | Result |
| --- | --- |
| Profile dialog and user icon (`d8c8bbd`, `a9d5eb1`) | Replaces our temporary nickname UI. The separate mic link uses the same singer name. |
| Autoplay preference (`fb0075e`) | Retained, including manual start when autoplay is off. |
| Master-player authorization (`8e677c7`) | Retained. |
| Splash notifications and mobile layout (`8dce2d6`, `7561b60`, `c69e486`) | Retained. |
| Managed yt-dlp (`4e6f529`) | Retained; Android still packages its compatible tools. |
| Vitest, Node 22, PR-title checks and security policy (`81174b8`, `4e52565`, `2fad083`, `6f7a194`) | Retained in upstream. Android checks its adapted player separately. |

- Blank-password automatic admin access already exists upstream; Android uses that behavior.
- Upstream has no storage-quota replacement in this reviewed range.
- Checked patches stop the build on incompatible upstream changes. The updater does not silently drop Android features.
- The weekly updater now checks the original upstream directly, then builds, tests and signs a release.

## Validation

- The phone-free fork with stock playback passed 1,639 Python tests, nine subtests, 66 upstream JS tests and the storage browser checks before migration.
- The optional translation tests were skipped because `polib` was not installed.
- Android checks storage cleanup and preferences, phone routes and admission limits, browser controls, source handoffs, PCM buffering and release automation against the generated sources.
- All 186 prepared app files match the pre-migration output byte for byte. The 30 focused Python tests, 20 automation tests, three browser checks and native PCM checks pass with the official upstream pin.
- Release publication also requires Android lint, Android TV emulator integration tests and signing verification.
- This repository change does not measure voice latency or establish a stock playback bug.
