# Contribution review

- Reviewed on 2026-10-20: all 24 fork-only master commits, all 52 Android main commits, existing feature-branch copies, and 12 upstream commits since the original Android pin.
- Review baseline: fork `4245483`, Android `b7484bf`, upstream `4e525655fe0a633e380f6c3ed8beaa4b295cfb20`.
- Existing master/main history, tags and older feature branches are preserved. No force push.

## Ownership

| Repository | Contents |
| --- | --- |
| `nabekhan/pikaraoke` | Shared phone-mic UI/API/protocol, capacity preference, storage quota, playback fix. |
| `nabekhan/pikaraoke-android` | Android host, packaging, TV controls, runtime adapters, certificates, WebRTC receiver, AAudio/AudioTrack output, device tests and releases. |

## Contribution branches

| Branch | Commit | Scope |
| --- | --- | --- |
| [contrib/phone-microphones](https://github.com/nabekhan/pikaraoke/tree/contrib/phone-microphones) | `9b421ad` | Phone mic web interface, guest API and backend contract. No Android source or desktop receiver. |
| [contrib/song-storage-limit](https://github.com/nabekhan/pikaraoke/tree/contrib/song-storage-limit) | `a823b47` | Song-folder MB/GB limit and startup cleanup. |
| [fix/player-source-handoff](https://github.com/nabekhan/pikaraoke/tree/fix/player-source-handoff) | `b214557` | Media-source teardown and stale-callback guards, including upstream Vitest adaptation. |

- Each branch has one commit directly on reviewed upstream. The three features are independent; fork automation is excluded.
- The older `feature/phone-microphones` and `feature/song-storage` branches contain intermediate commits. Use the new branches for contribution.
- The combined fork retains the features and merges their branch ancestry.
- Microphone streaming still needs a platform receiver. The Android app provides one; this reorganization does not add a desktop receiver.
- Storage cleanup uses POSIX directory-descriptor operations. Unsupported platforms report an error and leave files untouched.

## Upstream overlap

- Upstream replaces our temporary singer-name icon with the Profile dialog and official user icon. The mic link remains separate and uses the same name cookie.
- The storage quota, browser mic protocol and media-source cleanup have no upstream replacements in the reviewed range.
- Blank-password automatic admin access already exists upstream. Android should set its default through that auth implementation.
- Managed desktop yt-dlp does not replace Android packaging or the Android updater.
- The rejected phone-speaker output and superseded intermediate gain settings are absent from contribution patches.

| Upstream commit | Change | Decision |
| --- | --- | --- |
| [4e6f529](https://github.com/vicwomg/pikaraoke/commit/4e6f529dfbc7f5a07b6387adb3a6fd96da11e6d1) | feat: self-updating yt-dlp via managed binary (#996) | Retain managed yt-dlp. Android/ARM32 asset selection falls back to packaged module; Android AAR updater remains needed. |
| [6f7a194](https://github.com/vicwomg/pikaraoke/commit/6f7a194fd013eea4eca7453a23bce4906b2df409) | docs: add a security policy (#1002) | Retain upstream security documentation. |
| [8e677c7](https://github.com/vicwomg/pikaraoke/commit/8e677c70d7e7dc32d74420fcb25c0d45bfe44285) | fix: gate end_song on the master splash (#993) | Retain server master-splash authorization; client source-generation guards solve a separate issue. |
| [7561b60](https://github.com/vicwomg/pikaraoke/commit/7561b604bd90488dfcc228cfbfe0671d0621ef37) | refactor: consolidate mobile table padding (#1010) | Retain upstream mobile padding. |
| [fb0075e](https://github.com/vicwomg/pikaraoke/commit/fb0075e79ad5dfd6f170ca5d3a4c61116ebd7104) | feat: add an autoplay preference, off for manual song start (#1008) | Retain autoplay (default on). Merge storage/mic preferences and source-lifecycle fix without removing manual-start behavior. |
| [a9d5eb1](https://github.com/vicwomg/pikaraoke/commit/a9d5eb1228e0789e8fc6f10e834899fcddec3468) | chore: add bell and user icons to fontello font (#1013) | Use upstream user icon; remove our temporary inline user SVG. |
| [8dce2d6](https://github.com/vicwomg/pikaraoke/commit/8dce2d6cd609b84aaae6000870bd79026a37285b) | fix: stack overlapping splash notifications (#1012) | Retain upstream notification stack; source cleanup does not replace it. |
| [2fad083](https://github.com/vicwomg/pikaraoke/commit/2fad0838f02ae7b7b13d7672ef604667a74d94bb) | ci: lint PR titles as conventional commits (#1014) | Retain upstream PR-title CI; excluded from the feature patch itself. |
| [81174b8](https://github.com/vicwomg/pikaraoke/commit/81174b806c1c5d73219af362c454bdefdda6a943) | test: add a vitest suite for the splash screen protocol (#988) | Retain upstream Vitest suite; adapt media fake/assertions for source ownership and playing events. |
| [d8c8bbd](https://github.com/vicwomg/pikaraoke/commit/d8c8bbdb2095f260efe0254d0a1748756e2e44bd) | feat: name yourself from the navbar, in a dialog (#1016) | Use upstream Profile dialog and singer identity flow; keep separate icon-only mic link and shared user cookie. |
| [c69e486](https://github.com/vicwomg/pikaraoke/commit/c69e48615a4e34e95264b05f28a8a46f744ae790) | test: update splash vitest for current notifications (#1020) | Retain notification test updates. |
| [4e52565](https://github.com/vicwomg/pikaraoke/commit/4e525655fe0a633e380f6c3ed8beaa4b295cfb20) | chore: run JS tests on vitest 5 under node 22 (#1022) | Retain Node 22 / Vitest 5 toolchain; added browser checks run under npm test. |

## Fork commit inventory

| Commit | Change | Decision |
| --- | --- | --- |
| [a344b60](https://github.com/nabekhan/pikaraoke/commit/a344b606f9bfb596fcae3e1f08eeb072ee2fed63) | feat: add phone microphone UI and receiver integration | Split: portable mic UI/API in mic branch; Android receiver moved to Android repo. |
| [ea6351f](https://github.com/nabekhan/pikaraoke/commit/ea6351f11c44d916b2548949490619a49c2e06d6) | feat: limit song storage with startup cleanup | Consolidated into storage branch. |
| [90e728e](https://github.com/nabekhan/pikaraoke/commit/90e728e907cfe2883901dad1212a1e42c756a7b1) | ci: check fork features and sync original PiKaraoke | Fork maintenance only; excluded from contribution branches. |
| [22c9c5f](https://github.com/nabekhan/pikaraoke/commit/22c9c5f0bfff4c167ae936989af6114f1b0c09cd) | fix: stop quota cleanup when a subtree cannot be read | Storage branch: fail closed on unreadable subtrees. |
| [6431eae](https://github.com/nabekhan/pikaraoke/commit/6431eae8bea84b4c64898c09f0384bbd42594a5a) | fix: isolate cleanup journals by song folder | Storage branch: folder-specific cleanup journal. |
| [e9475ed](https://github.com/nabekhan/pikaraoke/commit/e9475ed005343ca058b9b0efb0783c74b1557d68) | fix: identify Android runtime imports to desktop lint | Android import/lint exception moves with adapter; absent from contribution branches. |
| [ed5a211](https://github.com/nabekhan/pikaraoke/commit/ed5a21192a05a5c6dde24aab036ffb75cc0928ea) | fix: bind storage form once during SPA navigation | Storage branch: bind form once under SPA navigation. |
| [0966581](https://github.com/nabekhan/pikaraoke/commit/0966581b4f1892ced2560241226348d7ebc33706) | test: assert one storage request after script replay | Storage branch: replay regression test. |
| [55d9af6](https://github.com/nabekhan/pikaraoke/commit/55d9af6f7e9ad982f299c8f676b0b0b9c4b91a87) | fix: raise phone mic gain and reduce buffered audio latency | Split: smaller browser packets in mic branch; jitter buffer and gain in Android repo. |
| [c1c805e](https://github.com/nabekhan/pikaraoke/commit/c1c805e4867dc9599acdf866d82a2365406e3a0d) | ci: check receiver latency budget with synthetic PCM | Android receiver benchmark checks moved to Android repo. |
| [01c6907](https://github.com/nabekhan/pikaraoke/commit/01c6907a62cd4b05241ff604901406cd93d5d28a) | fix: preserve boosted mic gain through final output limiting | Android mixer/limiter moved to Android repo. |
| [a75ade1](https://github.com/nabekhan/pikaraoke/commit/a75ade133f0718f4b8270803da6cb562544dcdaf) | ci: include final microphone output stage in PCM checks | Android output benchmark checks moved to Android repo. |
| [ce9dcd0](https://github.com/nabekhan/pikaraoke/commit/ce9dcd01525ad9951971b7128e843f27e79d6a0e) | fix: amplify phone microphones above raw capture level | Android input gain moved to Android repo. |
| [40cdfd0](https://github.com/nabekhan/pikaraoke/commit/40cdfd03e07755afe994dcc67607bf62fab6b6e4) | feat: add phone mic control lock and Android full screen | Mic branch: lock controls and Android phone browser fullscreen. |
| [5a4e18b](https://github.com/nabekhan/pikaraoke/commit/5a4e18bfba0b7d47a2af40e9b53e97141c61496a) | fix: keep phone mic output alive during HDMI standby | Android standby handling moved to Android repo. |
| [fae0d4a](https://github.com/nabekhan/pikaraoke/commit/fae0d4ab90cefd79c635363348c6fe152b24197f) | fix: recover phone mic playback after standby and increase gain | Android wake recovery/gain moved to Android repo. |
| [ce381a5](https://github.com/nabekhan/pikaraoke/commit/ce381a55aa2c68081007fbf0d47b9ee21eabffe7) | fix: refresh microphone assets after APK updates | Mic branch: content-based asset cache version. |
| [8367565](https://github.com/nabekhan/pikaraoke/commit/8367565c55a597bbabe72d28b1b65aeeea6eb461) | fix: use native low-latency phone mic output and reduce gain | Android AAudio/AudioTrack receiver moved to Android repo. |
| [641abeb](https://github.com/nabekhan/pikaraoke/commit/641abebe70028f8ac0e15899bea47e26c998d9e1) | feat: make phone mic capacity configurable with a default of two | Split: generic mic preference/UI in mic branch; host enforcement in Android repo. |
| [f99f775](https://github.com/nabekhan/pikaraoke/commit/f99f775f370f43199d54dad381adb4306ff57deb) | fix: serialize mic admission with limit changes | Split: preference mutation lock in mic branch; Android admission enforcement in Android repo. |
| [efff829](https://github.com/nabekhan/pikaraoke/commit/efff829cd65c508da669dbdc54517b48602d5c4d) | test: check dynamically restored mic preference | Android adapter preference regression moved to Android repo. |
| [458a73b](https://github.com/nabekhan/pikaraoke/commit/458a73ba5f125e331e66d67340cd10916d79620d) | feat: add local phone speaker output for microphones | Rejected phone-speaker experiment; omitted from all contribution patches. |
| [8fe0098](https://github.com/nabekhan/pikaraoke/commit/8fe0098f33f42f38b454da4d21efbf94348738fd) | fix: remove phone speaker output and start mics at 30 percent | Mic branch retains final TV-directed UI, lifecycle guards and 30% default; no experiment code. |
| [4245483](https://github.com/nabekhan/pikaraoke/commit/4245483fa515b0d3a5e46c97f508b4094a43eff6) | fix: release old video sources between queued songs | Separate player-source fix branch; excluded from mic branch. |

## Android commit inventory

| Commit | Change | Decision |
| --- | --- | --- |
| [a8d2086](https://github.com/nabekhan/pikaraoke-android/commit/a8d2086cff64671d0bfe096d9c0ef6df59029fca) | Add standalone Android TV host around pinned PiKaraoke upstream | Keep Android host, packaging, device checks or maintenance. |
| [7f1ca16](https://github.com/nabekhan/pikaraoke-android/commit/7f1ca1656bd70a1a4053bdff4fff6b41ab8bc0af) | Harden integration checks and refresh CI SDK installation | Keep Android host, packaging, device checks or maintenance. |
| [88da6f3](https://github.com/nabekhan/pikaraoke-android/commit/88da6f3b7b11703edf4c814d7e6f0da52590a8c1) | Fix Android startup ordering, port conflicts and interrupted runtime caches | Keep Android host, packaging, device checks or maintenance. |
| [359ccac](https://github.com/nabekhan/pikaraoke-android/commit/359ccac11826b94d07d6472ea1b860eece918d3b) | Add on-TV password recovery and verify the complete download-to-playback path | Keep Android host, packaging, device checks or maintenance. |
| [5cf24df](https://github.com/nabekhan/pikaraoke-android/commit/5cf24df9876f846a2e49f66dd134653de2896c4a) | Keep bundled JS runtime selection intact and handle startup failures | Keep Android host, packaging, device checks or maintenance. |
| [1e6c824](https://github.com/nabekhan/pikaraoke-android/commit/1e6c8244add6c0b19296f2c5f8109f49eaffb273) | Record Android TV runtime evidence and refine D-pad navigation | Keep Android host, packaging, device checks or maintenance. |
| [9dfb741](https://github.com/nabekhan/pikaraoke-android/commit/9dfb741d7b1c40ef7836cc8e04b2a74e971effc0) | Document signed release verification and package license notices | Keep Android host, packaging, device checks or maintenance. |
| [cd463e3](https://github.com/nabekhan/pikaraoke-android/commit/cd463e3a2b52b40ca47251d8fc81826deedac1a5) | Record passing x86 Android TV CI and signed YouTube playback | Keep Android host, packaging, device checks or maintenance. |
| [6709d80](https://github.com/nabekhan/pikaraoke-android/commit/6709d80155e935b39ebdc28d417b0d1014788d7b) | Preserve runtime evidence in release before local cleanup | Keep Android host, packaging, device checks or maintenance. |
| [4cb004c](https://github.com/nabekhan/pikaraoke-android/commit/4cb004cc04a0586dfecb63b2e13bf89386836396) | Automate tested, isolated signed Android updates | Keep Android host, packaging, device checks or maintenance. |
| [154e21d](https://github.com/nabekhan/pikaraoke-android/commit/154e21d85c8ee22ad787574db6537dcc5fbfac4a) | Recover untagged draft releases and guard successful reruns | Keep Android host, packaging, device checks or maintenance. |
| [4da6175](https://github.com/nabekhan/pikaraoke-android/commit/4da6175de30743a544d839c2dfb41ff0199b6ba4) | Reject ambiguous recovery drafts across release pages | Keep Android host, packaging, device checks or maintenance. |
| [7b02849](https://github.com/nabekhan/pikaraoke-android/commit/7b028499fe13c39d9928b7ed13ef49439b1ece0d) | Preserve source provenance and support full workflow reruns | Keep Android host, packaging, device checks or maintenance. |
| [0c8f77f](https://github.com/nabekhan/pikaraoke-android/commit/0c8f77fbcd09abd3417808a6d152665401d0211d) | Update tested Android release 1.23.0-android.2 | Keep Android release provenance. |
| [4250a9c](https://github.com/nabekhan/pikaraoke-android/commit/4250a9ccb3e5a0732a7bc2c9f847473814d80870) | Simplify README to basic instructions | Keep Android host, packaging, device checks or maintenance. |
| [d852a56](https://github.com/nabekhan/pikaraoke-android/commit/d852a56b95d6940ef9942534e17606ad616f6e2c) | Clarify optional local microphone passthrough | Keep Android host, packaging, device checks or maintenance. |
| [47529fe](https://github.com/nabekhan/pikaraoke-android/commit/47529fe8dfcf9d1a9284a179b2f0c18288333630) | Add four browser microphone slots and local HTTPS prototype | Split: generic phone UI/API now on fork; Android receiver/TLS remains here. |
| [0545c01](https://github.com/nabekhan/pikaraoke-android/commit/0545c01ada738e4d950b36e6a15ccfa4d0fd2e41) | Isolate WebRTC packages and exercise four-mic transport and TLS | Keep Android host, packaging, device checks or maintenance. |
| [00ae4be](https://github.com/nabekhan/pikaraoke-android/commit/00ae4be8acc735111b0f0e47ee0979abd2c41a9a) | Harden mic lifecycle and verify trusted HTTPS room access | Split: final browser lifecycle on fork; Android/TLS lifecycle remains here. |
| [e4ae0ac](https://github.com/nabekhan/pikaraoke-android/commit/e4ae0ac73e460ce882395507885b72c25dea4d6d) | Check browser microphone startup, cancellation and packet delivery | Generic browser regression moved to fork; APK integration evidence remains here. |
| [521f986](https://github.com/nabekhan/pikaraoke-android/commit/521f9866dbb331d06702f5eb9212a58a39e85983) | Serialize data-channel callbacks and retain emulator diagnostics | Keep Android host, packaging, device checks or maintenance. |
| [e329285](https://github.com/nabekhan/pikaraoke-android/commit/e329285a1648586a2b9eaa80ed5f3bc472fddace) | Close unstarted HTTP listeners safely on startup failure | Keep Android host, packaging, device checks or maintenance. |
| [ad9fe7d](https://github.com/nabekhan/pikaraoke-android/commit/ad9fe7da998dd7f322693a8654c2e2d79a3df730) | Report embedded server startup failures in device test | Keep Android host, packaging, device checks or maintenance. |
| [03d2f18](https://github.com/nabekhan/pikaraoke-android/commit/03d2f182ce05811824621cfadc1aab420a3f992c) | Reuse PiKaraoke singer names and simplify the mic interface | Generic singer-name/mic UI now in mic branch; old custom name icon superseded upstream. |
| [eaf5d4f](https://github.com/nabekhan/pikaraoke-android/commit/eaf5d4fc8b9efc8d9886076458113e1e3c0777a6) | Update tested Android release 1.23.0-android.3 | Keep Android release provenance. |
| [fd02e66](https://github.com/nabekhan/pikaraoke-android/commit/fd02e66b39b2804c0cba912bbffc0486d4bbf85c) | Simplify phone mic UI with deliberate slide control and theme inheritance | Generic mic UI now in mic branch; Android packaging remains here. |
| [aaa79d2](https://github.com/nabekhan/pikaraoke-android/commit/aaa79d2865e190f0b3b587c68a798de75758a1e3) | Publish a permanent universal APK download and Downloader code | Keep Android host, packaging, device checks or maintenance. |
| [44e9214](https://github.com/nabekhan/pikaraoke-android/commit/44e9214a459e3e632f3d22bb5f068b639549cb3a) | Bind latest-release recovery to the tagged source | Keep Android host, packaging, device checks or maintenance. |
| [15dd0ca](https://github.com/nabekhan/pikaraoke-android/commit/15dd0ca6d573c7ad60b064c8a7d49e4f6e2498cc) | Update tested Android release 1.23.0-android.4 | Keep Android release provenance. |
| [33fb907](https://github.com/nabekhan/pikaraoke-android/commit/33fb90701ec107aee1c577d9ba1738c2eab9187e) | Use the original PiKaraoke app icon from upstream | Keep Android host, packaging, device checks or maintenance. |
| [41bd0d7](https://github.com/nabekhan/pikaraoke-android/commit/41bd0d7dff7f6ebc7c4bcc3361a6b43160faa9f3) | Update tested Android release 1.23.0-android.5 | Keep Android release provenance. |
| [5dc4a4c](https://github.com/nabekhan/pikaraoke-android/commit/5dc4a4cdcf4aaa98f661c379dd1f3ee59aca4a8c) | Use PiKaraoke fork for shared features and receiver | Ownership decision superseded: generic features stay on fork; Android receiver returns here. |
| [7084ee2](https://github.com/nabekhan/pikaraoke-android/commit/7084ee2d2ee0879e9f6d6769ce2c1dd7c64cd465) | Update storage form navigation handling | Submodule pin for generic storage SPA fix; storage contribution contains final implementation. |
| [3cac8e6](https://github.com/nabekhan/pikaraoke-android/commit/3cac8e64f658a7a7cba62f581c2e3837af7dac4e) | Update tested Android release 1.23.0-android.6 | Keep Android release provenance. |
| [5a4a8ff](https://github.com/nabekhan/pikaraoke-android/commit/5a4a8ffe268dbb48b5d193a34e070cbd4cc5c57c) | Open TV player on startup and update phone microphone audio | Keep Android auto-player behavior; shared mic changes separated by platform. |
| [d07100b](https://github.com/nabekhan/pikaraoke-android/commit/d07100b02c33c6ccc6541a5e2b8971d6dd9af14a) | Start ADB before booting the Android TV emulator | Keep Android host, packaging, device checks or maintenance. |
| [7d1d5db](https://github.com/nabekhan/pikaraoke-android/commit/7d1d5db4675c193e259a9d4e93cc222696506bcc) | Update tested Android release 1.23.0-android.7 | Keep Android release provenance. |
| [fcd5f57](https://github.com/nabekhan/pikaraoke-android/commit/fcd5f575a28a47d4a5a3d7e2ca84d55a5da92c56) | Boost phone mic levels and add screen controls | Split: generic phone controls on fork; Android receiver gain stays here. |
| [d38017d](https://github.com/nabekhan/pikaraoke-android/commit/d38017d6ac2b71de216dfc6c17bdd05cd2f40adc) | Update tested Android release 1.23.0-android.8 | Keep Android release provenance. |
| [6399063](https://github.com/nabekhan/pikaraoke-android/commit/6399063caec8d6e675dac2937b00e27f59951155) | Keep phone mic audio running through TV standby | Keep Android receiver standby integration. |
| [07a8972](https://github.com/nabekhan/pikaraoke-android/commit/07a8972c1b74ef12eb00384e2559cf18c7839934) | Update tested Android release 1.23.0-android.9 | Keep Android release provenance. |
| [46c8ffa](https://github.com/nabekhan/pikaraoke-android/commit/46c8ffaa4335928fc8844843e026f72ca472be96) | Recover phone mic output after wake and raise mic gain | Keep Android receiver wake/audio integration. |
| [9e638f5](https://github.com/nabekhan/pikaraoke-android/commit/9e638f5d582269d997bb2ce91468ad414a605411) | Update tested Android release 1.23.0-android.10 | Keep Android release provenance. |
| [fce35b3](https://github.com/nabekhan/pikaraoke-android/commit/fce35b3bf9254d75e62d34393030bac754c6129d) | Build native low-latency phone microphone output | Keep Android native AAudio build/output integration. |
| [9ae2dcd](https://github.com/nabekhan/pikaraoke-android/commit/9ae2dcdb05062e9e48f78ee8b2824c003294fe22) | Default to two phone microphones with a configurable limit | Split: generic capacity preference on fork; Android receiver enforcement/testing here. |
| [0b66823](https://github.com/nabekhan/pikaraoke-android/commit/0b66823d52ad9465e42d97e7de458a6e3d931dad) | Pin the checked microphone configuration update | Submodule pin only; consolidated capacity feature is on fork. |
| [3d55f46](https://github.com/nabekhan/pikaraoke-android/commit/3d55f46b940387c5350e959f50eb8296cafdb7d6) | Check the configurable mic limit through the running room | Keep assembled Android room/capacity integration check. |
| [e191271](https://github.com/nabekhan/pikaraoke-android/commit/e1912719b4c25754a8f5ea0ee99da9e305bfec07) | Update tested Android release 1.23.0-android.11 | Keep Android release provenance. |
| [b60b028](https://github.com/nabekhan/pikaraoke-android/commit/b60b028415467b49e74dd9e7bbf1a95397dc6685) | Add phone speaker microphone output | Rejected phone-speaker experiment; no remaining implementation. |
| [313179d](https://github.com/nabekhan/pikaraoke-android/commit/313179df298c1679d1390814970b413f364c8542) | Update tested Android release 1.23.0-android.12 | Keep Android release provenance. |
| [81c2152](https://github.com/nabekhan/pikaraoke-android/commit/81c215205195d9f403e091db58a35abcd4eed1cb) | Fix playback transitions and remove phone speaker experiment | Split: generic source cleanup on fork; Android single-task/startup changes here; experiment removed. |
| [b7484bf](https://github.com/nabekhan/pikaraoke-android/commit/b7484bf2250571ae53382f23ed3793e154171c73) | Update tested Android release 1.23.0-android.13 | Keep Android release provenance. |

## Validation

- Phone branch: 1,626 Python tests passed; 66 upstream Vitest tests and browser mic checks passed.
- Storage branch: 1,639 Python tests plus nine subtests passed; 66 upstream Vitest tests and storage browser checks passed.
- Playback branch: 1,617 Python tests passed; 67 Vitest tests and source-handoff browser checks passed.
- Combined fork: 1,648 Python tests plus nine subtests passed; 67 Vitest tests and all three browser checks passed.
- Python runs skipped the existing translation-test module because optional `polib` was not installed.
- Android adapter: Python admission-race check, 20 release automation tests, Java PCM/latency checks and checked upstream source generation passed locally. Receiver C/Java/Python implementation files are byte-identical after relocation; CMake paths changed.
- Repository reorganization does not establish a new phone-to-speaker latency measurement.
