# Phone microphones

- Browser microphone UI, guest API and receiver interface.
- Uses the singer's existing PiKaraoke name.
- Starts at 30% volume. The receiver applies gain and reverb.
- Two microphones by default; Settings allows one to four.
- Requires HTTPS and microphone permission. Song browsing and queueing still work over HTTP.
- The mic icon appears only when a receiver installs the feature.
- The Android app includes the receiver; no desktop receiver is included.

## Receiver interface

- Register with `pikaraoke.lib.phone_mics.install(app, backend)` before serving requests.
- `backend.config()` supplies `secure_url`, `ca_url`, `ca_fingerprint` and `base_path`.
- `backend.certificate_path()` returns the public CA certificate path. Never return its private key.
- `backend.call(operation, *args)` handles `status`, `join`, `answer`, `controls`, `heartbeat` and `leave`.
- `join(name)` returns an unguessable session `id` and a one-based `slot`.
- `status()` returns `max` and `active`; each active entry has `slot`, `name` and `connected`. Session IDs must stay private.
- `answer(id, sdp)` returns the WebRTC answer `{type, sdp}`. Use host-only ICE on the local network.
- `controls(id, gain, muted, reverb)` receives gain from 0 to 2 and reverb from 0 to 3.
- Expire abandoned sessions; enforce the configured limit under `preferences.mutation_lock` when admitting a singer.
- Raise `PhoneMicError(message, status_code)` for errors safe to show to guests.
- Serve the same app over HTTPS, with a certificate trusted by the phone. Certificate creation and audio output belong to the receiver.

## Audio transport

- WebRTC data channel `audio`, unordered, `maxRetransmits: 0`.
- Each message contains a 16-byte header followed by mono signed PCM16 samples, little endian.
- Header: timestamp in microseconds (`uint64`), sequence (`uint16`), sample count (`uint16`), sample-rate code (`uint8`, 2 = 44.1 kHz, 3 = 48 kHz), sample bits (16), channel count (1), version (1).
- Normal capture packets contain 128 samples. Other capture rates are resampled to 48 kHz.
- The browser drops old capture callbacks and congested sends. Receivers should bound buffering rather than replay old audio.
- No promise of a particular acoustic latency. Phone capture, Wi-Fi and speaker hardware all contribute.

## Checks

- `python scripts/prepare_upstream.py`, then `PYTHONPATH="app/src/main/python:app/build/generated/python" python -m unittest discover -s app/src/test/phone-microphones/unit`
- `NODE_PATH=/path/to/jsdom/node_modules node app/src/test/phone-microphones/phone-mic-client.test.cjs`
- Optional transport benchmark: `npm install --no-save --package-lock=false playwright-core@1.64.1 ws@8.22.0`, then `CHROME_EXECUTABLE=/path/to/chrome node app/src/test/phone-microphones/benchmark_phone_mic.cjs`. Chrome must already be installed. Timing excludes real phone capture and speaker output.
