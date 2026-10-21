# Phone microphone latency

- Measured locally on 2026-10-20, Apple silicon macOS, Chrome 155 and JDK 17.
- [Raw measurements](benchmarks/phone-mic-2026-10-20.json).
- These are software tests. They do not measure the phone microphone, Wi-Fi, Android audio output, HDMI, Bluetooth, or speakers.
- The sample signal is generated locally. No microphone is recorded and no test sound is played through the speakers.

## Transport test

- `app/src/test/phone-microphones/benchmark_phone_mic.cjs` sends synthetic 997 Hz mono PCM16 through the real AudioWorklet and browser transports.
- Each case echoes 300 packets. The first 20 are excluded from timing statistics.
- Values below are echo round-trip time divided by two, an estimate of local one-way transport time. No network loss was injected.
- Every case returned all packets with their sample bytes unchanged.

| Transport | Frames per packet | Median (ms) | 95th percentile (ms) |
| --- | --- | --- | --- |
| WebRTC unordered, no retransmits | 256 | 0.30 | 0.55 |
| WebRTC unordered, no retransmits | 128 | 0.35 | 0.65 |
| WebRTC ordered, reliable | 256 | 0.30 | 0.65 |
| WebRTC ordered, reliable | 128 | 0.35 | 0.75 |
| WebSocket | 256 | 0.20 | 0.60 |
| WebSocket | 128 | 0.20 | 0.55 |

- The small local WebSocket advantage does not establish a lower latency on Wi-Fi. Its reliable TCP transport can hold newer audio behind a lost packet.
- Keep the current unreliable WebRTC channel. Native JackTrip/SonoBus clients would require a phone app; switching packet formats alone would not remove device or output latency.

Run with Node, `playwright-core`, `ws`, and an installed Chrome:

```sh
NODE_PATH=/path/to/node_modules CHROME_EXECUTABLE=/path/to/chrome node app/src/test/phone-microphones/benchmark_phone_mic.cjs
```

## Receiver test

- `PhoneMicLatencyCheck.java` sends timed PCM pulses through the actual `PhoneMicBuffer`, with a simulated 5 ms mixer schedule and seeded arrival jitter.
- The baseline is fork commit `0966581`, with 256-frame packets and a 20 ms receiver target.
- Updated settings use 128-frame packets and a 10 ms initial target. The target increases after underruns, up to 30 ms.
- The benchmark measures the pulse's source-to-mixer delay. It excludes WebRTC and Android output latency.

| Simulated arrival jitter | Baseline median (ms) | Updated median (ms) | Updated steady underruns |
| --- | --- | --- | --- |
| 0 ms | 25.00 | 14.46 | 0 |
| 0–3 ms | 25.42 | 14.83 | 0 |
| 0–8 ms | 29.90 | 19.29 | 0 |
| 0–15 ms | 38.48 | 23.96 | 0 |

```sh
javac -d /tmp/mic-check app/src/main/java/org/pikaraoke/tv/PhoneMicBuffer.java app/src/test/phone-mic/PhoneMicLatencyCheck.java
java -cp /tmp/mic-check PhoneMicLatencyCheck
```

## Changes

- Capture packet size: 256 → 128 frames (5.33 → 2.67 ms at 48 kHz).
- Initial receiver target: 20 → 10 ms, increasing after underruns.
- Maximum receiver queue: 80 → 40 ms.
- Browser send-queue cutoff: 4096 → 1024 bytes. Drop capture callbacks older than 20 ms.
- Request an Android output buffer of two device bursts, then increase it if the output underruns. Unsupported tuning leaves the device's buffer in use.
- `/api/phone-mics` reports the actual output-buffer frame count and output/receiver underruns for diagnosis.
- Output-buffer capacity is not a measurement of its occupied audio or physical latency.
- The final output limits individual peaks. A loud peak no longer turns down every sample in the block and cancels the gain boost.
- Phone input has an 18 dB preamp: 50% volume gives 8× the captured signal, 100% gives 16×. The final limiter bounds loud peaks. This adds no buffering. The mic starts at 30% volume.

## Native HDMI output prototype

- Google TV Streamer, Android 14, TV speakers, 2026-10-20.
- The previous AudioTrack path reported about 173 ms of output delay.
- AAudio shared mode on the same HDMI device reported about 17 ms with a synthetic silent signal. The buffer held 384 frames at 48 kHz (two device bursts).
- These are Android presentation-timestamp estimates, not phone-to-speaker acoustic measurements. They exclude phone capture, network transit, and processing after HDMI.
- Nonblocking writes are limited using frames written minus frames consumed. On this device, merely setting the smaller buffer still allowed writes to fill the larger capacity and raised the estimate to about 68 ms.
- The receiver keeps AudioTrack as a fallback where the low-latency native stream is unavailable. Device changes and standby reopen the output without removing phone connections.
- A later 30-second live phone sample had a median receiver queue of 28 ms and output estimate of 25 ms, with no new output underruns or restarts. The output buffer had adapted to 768 frames. Listening on iPhone/Safari was reported as roughly 0.5 seconds late but smooth; the full acoustic delay has not been measured.

## Sources

- [WebRTC data channels](https://www.w3.org/TR/webrtc/): ordering and retransmission settings.
- [RFC 8831](https://www.rfc-editor.org/rfc/rfc8831.html): SCTP transport for WebRTC data channels.
- [Android AAudio](https://developer.android.com/ndk/guides/audio/aaudio/aaudio): shared low-latency output, timestamps, and nonblocking writes.
- [Android AudioTrack](https://developer.android.com/reference/android/media/AudioTrack): output-buffer sizing and underrun counters.
- [Web Audio latency hints](https://developer.mozilla.org/en-US/docs/Web/API/AudioContext/AudioContext): hints may be ignored by the browser.
- [SonoBus user guide](https://github.com/sonosaurus/sonobus/blob/main/doc/SonoBus%20User%20Guide.md): jitter-buffer tuning.
