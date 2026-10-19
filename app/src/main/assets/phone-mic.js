(() => {
  'use strict';

  const config = window.phoneMicConfig || {};
  const basePath = (config.base_path || '').replace(/\/$/, '');
  const apiRoot = `${basePath}/api/phone-mics`;
  const $ = (id) => document.getElementById(id);
  const ui = {
    toggle: $('mic-toggle'), status: $('mic-status'), gain: $('gain'),
    gainValue: $('gain-value'), reverb: $('reverb'), reverbDescription: $('reverb-description'),
    mute: $('mute'), slots: $('slot-list'), slotCount: $('slot-count'), title: $('track-title'),
    user: $('track-user'), certificate: $('certificate-panel'), secureLink: $('secure-link'),
    caLink: $('ca-link'), level: document.querySelector('.level')
  };
  const state = { id: null, slot: null, pc: null, channel: null, stream: null, context: null, heartbeat: null, wakeLock: null, sequence: 0, active: false, stopping: false, muted: false, reverb: 0, lastInfo: null, startPromise: null };
  const reverbNames = ['Off', 'Room', 'Hall', 'Stage'];
  let startVersion = 0;
  const levelBars = Array.from(ui.level.querySelectorAll('i'));

  function setStatus(message, error = false) { ui.status.textContent = message; ui.status.classList.toggle('error', error); }
  function api(url = '', options = {}) {
    return fetch(`${apiRoot}${url}`, { headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options })
      .then(async (response) => {
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw Object.assign(new Error(body.error || `Request failed (${response.status})`), { status: response.status });
        return body;
      });
  }
  function setActive(active) {
    state.active = active;
    ui.toggle.classList.toggle('live', active);
    ui.toggle.setAttribute('aria-pressed', String(active));
    ui.toggle.querySelector('.toggle-label').textContent = active ? (state.muted ? 'Mic muted' : 'Stop mic') : 'Start mic';
    ui.mute.disabled = !active;
    document.body.classList.toggle('is-live', active);
  }
  function setMute(muted, announce = true) {
    state.muted = muted;
    ui.mute.setAttribute('aria-pressed', String(muted));
    ui.mute.querySelector('span').textContent = muted ? 'Unmute mic' : 'Mute mic';
    if (state.id) sendControls();
    if (announce && state.active) setStatus(muted ? 'Mic muted' : 'Microphone is live');
    setActive(state.active);
  }
  function refreshReverb() {
    ui.reverb.textContent = reverbNames[state.reverb];
    ui.reverb.setAttribute('aria-label', `Mic reverb: ${reverbNames[state.reverb]}`);
    ui.reverbDescription.textContent = state.reverb === 0 ? 'Dry' : `${reverbNames[state.reverb]} reverb`;
  }
  function sendControls() {
    if (!state.id) return;
    api(`/${encodeURIComponent(state.id)}/controls`, { method: 'POST', body: JSON.stringify({ gain: Number(ui.gain.value) / 100, muted: state.muted, reverb: state.reverb }) })
      .catch(() => { if (state.active) stopMic('Could not update the mic. Start it again.'); });
  }
  function renderInfo(info) {
    state.lastInfo = info;
    const max = info.max || 4;
    const active = Array.isArray(info.active) ? info.active : [];
    ui.slotCount.textContent = `${active.length} of ${max} in use`;
    ui.slots.replaceChildren(...Array.from({ length: max }, (_, index) => {
      const slot = index + 1;
      const mic = active.find((item) => Number(item.slot) === slot);
      const li = document.createElement('li');
      li.className = `slot${mic && mic.connected ? ' live' : ''}${mic && mic.muted ? ' muted' : ''}`;
      li.innerHTML = `<span class="slot-number">Mic ${slot}</span><span class="slot-name">${mic ? escapeHtml(mic.name || 'Phone') : 'Open'}</span><span class="slot-state">${mic ? (mic.connected ? (mic.muted ? 'Muted' : 'Live') : 'Connecting') : ''}</span>`;
      return li;
    }));
    const now = info.now_playing || {};
    ui.title.textContent = now.title || 'Nothing playing';
    ui.user.textContent = now.user || '';
    if (info.output_error && state.active) stopMic(info.output_error);
    if (!state.active && active.length >= max) setStatus('All four phone mics are in use', true);
  }
  function escapeHtml(value) { const node = document.createElement('span'); node.textContent = value; return node.innerHTML; }
  function singerName() {
    // PiKaraoke's user cookie is shared by the HTTP and HTTPS ports.
    const cookie = document.cookie.split(';').map(value => value.trim()).find(value => value.startsWith('user='));
    if (!cookie) return 'Singer';
    let name = cookie.slice(5);
    if (name.startsWith('"')) name = name.slice(1, -1);
    try { name = decodeURIComponent(name); } catch (_) {}
    return name.trim().slice(0, 48) || 'Singer';
  }
  async function refreshInfo() {
    try { renderInfo(await api()); }
    catch (error) { if (!state.active) setStatus('Could not reach PiKaraoke. Check this phone is on the same network.', true); }
  }
  function setLinks() {
    const search = `${basePath}/search`, queue = `${basePath}/queue`;
    $('add-song').href = search; $('queue-link').href = queue;
    if (config.ca_url) ui.caLink.href = config.ca_url;
    if (config.secure_url) ui.secureLink.href = config.secure_url;
    $('ca-fingerprint').textContent = config.ca_fingerprint || '';
  }
  function showCertificateOnboarding() {
    document.body.classList.add('needs-certificate');
    ui.certificate.hidden = false;
    ui.toggle.disabled = true;
    setStatus('Open the secure microphone link to continue', true);
  }
  function updateLevel(rms) {
    const count = state.muted || !state.active ? 0 : Math.min(levelBars.length, Math.round(Math.max(0, Math.min(1, rms * 7)) * levelBars.length));
    levelBars.forEach((bar, index) => { const on = index < count; bar.classList.toggle('on', on); bar.style.height = on ? `${6 + ((index % 4) * 4)}px` : '4px'; });
  }
  function rateEnum(rate) { return rate === 44100 ? 2 : 3; }
  function resampleTo48k(samples, sourceRate) {
    if (sourceRate === 48000 || sourceRate === 44100) return samples;
    const length = Math.max(1, Math.round(samples.length * 48000 / sourceRate));
    const output = new Float32Array(length);
    for (let i = 0; i < length; i += 1) {
      const position = i * (sourceRate / 48000), left = Math.floor(position), right = Math.min(left + 1, samples.length - 1), frac = position - left;
      output[i] = samples[left] * (1 - frac) + samples[right] * frac;
    }
    return output;
  }
  function writeTimestamp(view, timestamp) {
    const micros = Math.floor(timestamp * 1000);
    if (typeof view.setBigUint64 === 'function' && typeof BigInt === 'function') view.setBigUint64(0, BigInt(micros), true);
    else { view.setUint32(0, micros >>> 0, true); view.setUint32(4, Math.floor(micros / 4294967296) >>> 0, true); }
  }
  function sendPcm(samples, time) {
    if (!state.active || state.muted || !state.channel || state.channel.readyState !== 'open' || state.channel.bufferedAmount > 4096) return;
    if (Number.isFinite(time) && state.context.currentTime - time > .04) return;
    const sourceRate = state.context.sampleRate;
    const pcmSamples = resampleTo48k(samples, sourceRate);
    if (pcmSamples.length > 1024) return;
    const packet = new ArrayBuffer(16 + pcmSamples.length * 2);
    const view = new DataView(packet);
    writeTimestamp(view, performance.timeOrigin + performance.now());
    view.setUint16(8, state.sequence++ & 0xffff, true);
    view.setUint16(10, pcmSamples.length, true);
    view.setUint8(12, rateEnum(sourceRate));
    view.setUint8(13, 16); view.setUint8(14, 1); view.setUint8(15, 1);
    for (let i = 0; i < pcmSamples.length; i += 1) view.setInt16(16 + i * 2, Math.max(-1, Math.min(1, pcmSamples[i])) * 32767, true);
    try { state.channel.send(packet); } catch (_) { stopMic('Connection lost. Start the mic again.'); }
  }
  async function acquireWakeLock() { try { if ('wakeLock' in navigator) state.wakeLock = await navigator.wakeLock.request('screen'); } catch (_) {} }
  async function releaseWakeLock() { try { await state.wakeLock?.release(); } catch (_) {} finally { state.wakeLock = null; } }
  async function stopMic(message = 'Microphone stopped', release = true) {
    startVersion++;
    if (state.stopping) return;
    state.stopping = true;
    const id = state.id;
    clearInterval(state.heartbeat); state.heartbeat = null;
    try { state.channel?.close(); state.pc?.close(); } catch (_) {}
    state.stream?.getTracks().forEach((track) => track.stop());
    try { await state.context?.close(); } catch (_) {}
    state.channel = state.pc = state.stream = state.context = null; state.id = null; state.slot = null; state.sequence = 0;
    await releaseWakeLock(); setActive(false); updateLevel(0);
    if (release && id) api(`/${encodeURIComponent(id)}`, { method: 'DELETE' }).catch(() => api(`/${encodeURIComponent(id)}/leave`, { method: 'POST' }).catch(() => {}));
    setStatus(message);
    state.stopping = false;
    refreshInfo();
  }
  async function startMic() {
    if (state.startPromise) return state.startPromise;
    state.startPromise = (async () => {
      const version = ++startVersion;
      const check = () => { if (version !== startVersion) throw new Error('Microphone stopped'); };
      if (!window.isSecureContext) { showCertificateOnboarding(); return; }
      if (!navigator.mediaDevices?.getUserMedia || !window.RTCPeerConnection || !window.AudioWorkletNode) {
        setStatus('Update Safari or Chrome to use this microphone.', true); return;
      }
      const name = singerName();
      setStatus('Requesting microphone permission…'); ui.toggle.disabled = true;
      try {
        const info = await api(); check(); renderInfo(info);
        if (Array.isArray(info.active) && info.active.length >= (info.max || 4)) throw Object.assign(new Error('All four phone mics are in use'), { status: 409 });
        state.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false }, video: false });
        check();
        const reservation = await api('', { method: 'POST', body: JSON.stringify({ name }) });
        state.id = reservation.id; state.slot = reservation.slot;
        check();
        state.pc = new RTCPeerConnection();
        state.channel = state.pc.createDataChannel('audio', { ordered: false, maxRetransmits: 0 });
        try { state.context = new AudioContext({ sampleRate: 48000, latencyHint: 'interactive' }); }
        catch (_) { state.context = new AudioContext({ latencyHint: 'interactive' }); }
        await state.context.resume();
        check();
        await state.context.audioWorklet.addModule(`${basePath}/static/phone-mic-worklet.js`);
        check();
        const source = state.context.createMediaStreamSource(state.stream);
        const worklet = new AudioWorkletNode(state.context, 'phone-mic-processor');
        const silent = state.context.createGain(); silent.gain.value = 0;
        source.connect(worklet).connect(silent).connect(state.context.destination);
        worklet.port.onmessage = (event) => { updateLevel(event.data.rms); sendPcm(event.data.samples, event.data.time); };
        state.stream.getAudioTracks().forEach(track => {
          track.onended = () => { if (!state.stopping) stopMic('Microphone was interrupted. Start it again.'); };
          track.onmute = () => { if (state.active && !state.stopping) stopMic('Microphone was interrupted. Start it again.'); };
        });
        state.context.onstatechange = () => { if (state.active && state.context?.state !== 'running' && !state.stopping) stopMic('Audio was interrupted. Start the mic again.', true); };
        const offer = await state.pc.createOffer(); await state.pc.setLocalDescription(offer);
        await waitForIceComplete(state.pc);
        check();
        const answer = await api(`/${encodeURIComponent(state.id)}/offer`, { method: 'POST', body: JSON.stringify({ sdp: state.pc.localDescription.sdp }) });
        check();
        await state.pc.setRemoteDescription({ type: answer.type || 'answer', sdp: answer.sdp });
        await waitForOpen(state.channel);
        check();
        if (state.context.state !== 'running') throw new Error('Audio was interrupted. Start the mic again.');
        state.pc.onconnectionstatechange = () => { if (state.pc && state.active && ['failed', 'disconnected', 'closed'].includes(state.pc.connectionState)) stopMic('Connection lost. Start the mic again.', true); };
        state.channel.onclose = () => { if (state.active && !state.stopping) stopMic('Connection lost. Start the mic again.'); };
        state.heartbeat = setInterval(() => { if (state.id) api(`/${encodeURIComponent(state.id)}/heartbeat`, { method: 'POST', body: '{}' }).catch(() => stopMic('Mic session expired. Start again.', false)); }, 10000);
        setActive(true); setMute(false, false); sendControls(); await acquireWakeLock(); setStatus(`Microphone ${state.slot} is live`); refreshInfo();
      } catch (error) {
        const permission = error.name === 'NotAllowedError' || error.name === 'SecurityError';
        await stopMic(permission ? 'Microphone access was not allowed. Allow it in browser settings, then try again.' : error.message || 'Could not start the microphone.', true);
      } finally { ui.toggle.disabled = false; }
    })();
    try { await state.startPromise; } finally { state.startPromise = null; }
  }
  function waitForIceComplete(pc) {
    if (pc.iceGatheringState === 'complete') return Promise.resolve();
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { pc.removeEventListener('icegatheringstatechange', done); reject(new Error('Connection timed out. Check your Wi-Fi and try again.')); }, 10000);
      const done = () => { if (pc.iceGatheringState === 'complete') { clearTimeout(timer); pc.removeEventListener('icegatheringstatechange', done); resolve(); } };
      pc.addEventListener('icegatheringstatechange', done);
    });
  }
  function waitForOpen(channel) {
    if (channel.readyState === 'open') return Promise.resolve();
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('Could not reach the TV. Check both devices are on the same Wi-Fi.')), 10000);
      channel.onopen = () => { clearTimeout(timer); resolve(); };
      channel.onerror = () => { clearTimeout(timer); reject(new Error('Microphone connection failed. Try again.')); };
    });
  }
  ui.toggle.addEventListener('click', () => state.active ? stopMic() : startMic());
  ui.mute.addEventListener('click', () => setMute(!state.muted));
  ui.gain.addEventListener('input', () => { ui.gainValue.textContent = `${ui.gain.value}%`; sendControls(); });
  ui.reverb.addEventListener('click', () => { state.reverb = (state.reverb + 1) % 4; refreshReverb(); sendControls(); });
  $('close-button').addEventListener('click', async () => { await stopMic('Microphone stopped'); history.length > 1 ? history.back() : (window.location.href = `${basePath}/` || '/'); });
  window.addEventListener('pagehide', () => {
    if (state.id && navigator.sendBeacon) navigator.sendBeacon(`${apiRoot}/${encodeURIComponent(state.id)}/leave`, new Blob(['{}'], { type: 'application/json' }));
    stopMic('Microphone stopped');
  });
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible' && state.active) acquireWakeLock(); });
  ui.mute.disabled = true; refreshReverb(); setLinks(); refreshInfo(); setInterval(refreshInfo, 5000);
  if (!window.isSecureContext) showCertificateOnboarding();
})();
