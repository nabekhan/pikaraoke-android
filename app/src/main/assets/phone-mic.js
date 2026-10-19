(() => {
  'use strict';

  const config = window.phoneMicConfig || {};
  const basePath = (config.base_path || '').replace(/\/$/, '');
  const apiRoot = `${basePath}/api/phone-mics`;
  const $ = (id) => document.getElementById(id);
  const ui = {
    toggle: $('mic-toggle'), status: $('mic-status'), gain: $('gain'),
    gainValue: $('gain-value'), reverb: $('reverb'), volumeToggle: $('volume-toggle'),
    volumePanel: $('volume-panel'), reverbPanel: $('reverb-panel'),
    slots: $('slot-list'), certificate: $('certificate-panel'), secureLink: $('secure-link'),
    caLink: $('ca-link'), level: document.querySelector('.level')
  };
  const state = { id: null, slot: null, pc: null, channel: null, stream: null, context: null, heartbeat: null, wakeLock: null, sequence: 0, active: false, requested: false, stopping: false, reverb: 0, lastInfo: null, startPromise: null };
  const reverbNames = ['Off', 'Room', 'Hall', 'Stage'];
  let startVersion = 0;
  const levelBars = Array.from(ui.level.querySelectorAll('i'));

  function setStatus(message, error = false) { ui.status.textContent = message; ui.status.hidden = !message; ui.status.classList.toggle('error', error); }
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
    setRequested(active);
    document.body.classList.toggle('is-live', active);
  }
  function setRequested(requested) {
    state.requested = requested;
    ui.toggle.style.setProperty('--mic-position', requested ? 1 : 0);
    ui.toggle.setAttribute('aria-valuenow', requested ? '1' : '0');
    ui.toggle.setAttribute('aria-valuetext', requested ? (state.active ? 'On. Slide down to turn off.' : 'Connecting. Slide down to cancel.') : 'Off. Slide up to turn on.');
    ui.toggle.setAttribute('aria-busy', String(requested && !state.active));
  }
  function refreshReverb() {
    ui.reverb.setAttribute('aria-label', `Mic reverb: ${reverbNames[state.reverb]}`);
    ui.reverb.classList.toggle('enabled', state.reverb !== 0);
    document.querySelectorAll('[data-reverb]').forEach(button => {
      const selected = Number(button.dataset.reverb) === state.reverb;
      button.setAttribute('aria-pressed', String(selected));
      button.classList.toggle('is-link', selected);
    });
  }
  function sendControls() {
    if (!state.id) return;
    api(`/${encodeURIComponent(state.id)}/controls`, { method: 'POST', body: JSON.stringify({ gain: Number(ui.gain.value) / 100, muted: false, reverb: state.reverb }) })
      .catch(() => { if (state.active) stopMic('Could not update the mic. Start it again.'); });
  }
  function renderInfo(info) {
    state.lastInfo = info;
    const max = info.max || 4;
    const active = Array.isArray(info.active) ? info.active : [];
    ui.slots.replaceChildren(...Array.from({ length: max }, (_, index) => {
      const slot = index + 1;
      const mic = active.find((item) => Number(item.slot) === slot);
      const li = document.createElement('li');
      li.className = `slot${mic && mic.connected ? ' live' : ''}${mic && mic.muted ? ' muted' : ''}`;
      const status = mic ? (mic.connected ? (mic.muted ? 'muted' : 'live') : 'connecting') : 'available';
      li.setAttribute('aria-label', `Mic ${slot}: ${mic ? (mic.name || 'Phone') + ', ' : ''}${status}`);
      li.title = li.getAttribute('aria-label');
      return li;
    }));
    if (info.output_error && state.active) stopMic(info.output_error);
    if (!state.requested && active.length >= max) setStatus('All four mics are in use.', true);
    else if (active.length < max && ui.status.textContent === 'All four mics are in use.') setStatus('');
  }
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
    try {
      const info = await api();
      if (ui.status.textContent === 'TV unavailable. Check your Wi-Fi.') setStatus('');
      renderInfo(info);
    }
    catch (error) { if (!state.active) setStatus('TV unavailable. Check your Wi-Fi.', true); }
  }
  function setLinks() {
    $('back-link').href = `${basePath}/`;
    if (config.ca_url) ui.caLink.href = config.ca_url;
    if (config.secure_url) ui.secureLink.href = config.secure_url;
    const agent = navigator.userAgent;
    $('certificate-instructions').textContent = /iPhone|iPad|iPod/.test(agent) || (/Macintosh/.test(agent) && navigator.maxTouchPoints > 1)
      ? 'Settings → Profile Downloaded → Install. Then General → About → Certificate Trust Settings → enable PiKaraoke.'
      : /Android/.test(agent) ? 'Settings → search “CA certificate” → Install.'
        : 'Install this certificate as a trusted CA.';
  }
  function showCertificateOnboarding() {
    ui.certificate.hidden = false;
    if (ui.certificate.showModal) ui.certificate.showModal();
    else ui.certificate.setAttribute('open', '');
    setRequested(false); setStatus('');
  }
  async function openSecureMic(check) {
    setRequested(true); setStatus('Opening secure mic…');
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 2500);
    try {
      // A no-cors probe verifies TLS without bypassing certificate checks.
      await fetch(config.secure_url, { mode: 'no-cors', credentials: 'omit', cache: 'no-store', signal: controller.signal });
      check(); window.location.assign(config.secure_url);
    } catch (_) {
      check(); showCertificateOnboarding();
    } finally { clearTimeout(timer); }
  }
  function updateLevel(rms) {
    const count = !state.active ? 0 : Math.min(levelBars.length, Math.round(Math.max(0, Math.min(1, rms * 7)) * levelBars.length));
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
    if (!state.active || !state.channel || state.channel.readyState !== 'open' || state.channel.bufferedAmount > 4096) return;
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
  async function stopMic(message = '', release = true) {
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
      if (!window.isSecureContext) {
        try { await openSecureMic(check); } catch (_) { /* Cancelled while checking HTTPS. */ }
        return;
      }
      if (!navigator.mediaDevices?.getUserMedia || !window.RTCPeerConnection || !window.AudioWorkletNode) {
        setRequested(false); setStatus('Update Safari or Chrome to use this microphone.', true); return;
      }
      const name = singerName();
      setRequested(true);
      setStatus('Allow microphone access');
      try {
        const info = await api(); check(); renderInfo(info);
        if (Array.isArray(info.active) && info.active.length >= (info.max || 4)) throw Object.assign(new Error('All four phone mics are in use'), { status: 409 });
        state.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false }, video: false });
        check();
        setStatus('Connecting…');
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
        setActive(true); sendControls(); await acquireWakeLock(); setStatus(''); refreshInfo();
      } catch (error) {
        const permission = error.name === 'NotAllowedError' || error.name === 'SecurityError';
        await stopMic(permission ? 'Microphone access was not allowed. Allow it in browser settings, then try again.' : error.message || 'Could not start the microphone.', true);
      }
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
  let drag = null;
  function requestMic(on) {
    if (on === state.requested || state.stopping) { setRequested(state.requested); return; }
    if (on) startMic(); else stopMic();
  }
  ui.toggle.addEventListener('pointerdown', event => {
    if (event.button !== 0 || drag || state.stopping || ui.toggle.getAttribute('aria-disabled') === 'true') return;
    event.preventDefault();
    ui.toggle.focus();
    const start = state.requested ? 1 : 0;
    drag = { id: event.pointerId, y: event.clientY, start, position: start, travel: 88 };
    ui.toggle.setPointerCapture?.(event.pointerId);
    ui.toggle.classList.add('dragging');
  });
  ui.toggle.addEventListener('pointermove', event => {
    if (!drag || event.pointerId !== drag.id) return;
    drag.position = Math.max(0, Math.min(1, drag.start + (drag.y - event.clientY) / drag.travel));
    ui.toggle.style.setProperty('--mic-position', drag.position);
  });
  function endDrag(event, cancelled) {
    if (!drag || event.pointerId !== drag.id) return;
    const gesture = drag; drag = null;
    gesture.position = Math.max(0, Math.min(1, gesture.start + (gesture.y - event.clientY) / gesture.travel));
    ui.toggle.classList.remove('dragging');
    if (ui.toggle.hasPointerCapture?.(event.pointerId)) ui.toggle.releasePointerCapture(event.pointerId);
    // Taps and partial swipes snap back without toggling capture.
    if (!cancelled && Math.abs(event.clientY - gesture.y) >= gesture.travel * .6) {
      if (gesture.start === 0 && gesture.position >= .85) { requestMic(true); return; }
      if (gesture.start === 1 && gesture.position <= .15) { requestMic(false); return; }
    }
    setRequested(state.requested);
  }
  ui.toggle.addEventListener('pointerup', event => endDrag(event, false));
  ui.toggle.addEventListener('pointercancel', event => endDrag(event, true));
  ui.toggle.addEventListener('lostpointercapture', event => endDrag(event, true));
  ui.toggle.addEventListener('keydown', event => {
    if (['ArrowUp', 'ArrowRight', 'End', 'ArrowDown', 'ArrowLeft', 'Home'].includes(event.key)) {
      event.preventDefault();
      requestMic(['ArrowUp', 'ArrowRight', 'End'].includes(event.key));
    }
  });
  function closePanels() {
    ui.volumePanel.hidden = ui.reverbPanel.hidden = true;
    ui.volumeToggle.setAttribute('aria-expanded', 'false'); ui.reverb.setAttribute('aria-expanded', 'false');
  }
  function togglePanel(button, panel) {
    const open = panel.hidden; closePanels(); panel.hidden = !open; button.setAttribute('aria-expanded', String(open));
  }
  ui.volumeToggle.addEventListener('click', () => togglePanel(ui.volumeToggle, ui.volumePanel));
  ui.reverb.addEventListener('click', () => togglePanel(ui.reverb, ui.reverbPanel));
  ui.gain.addEventListener('input', () => {
    ui.gainValue.textContent = `${ui.gain.value}%`;
    ui.volumeToggle.setAttribute('aria-label', `Microphone volume: ${ui.gain.value}%`); sendControls();
  });
  document.querySelectorAll('[data-reverb]').forEach(button => button.addEventListener('click', () => {
    state.reverb = Number(button.dataset.reverb); refreshReverb(); sendControls(); closePanels();
  }));
  document.addEventListener('click', event => { if (!event.target.closest('.effect')) closePanels(); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') closePanels(); });
  function closeCertificateSetup() {
    if (ui.certificate.close && ui.certificate.open) ui.certificate.close();
    else { ui.certificate.removeAttribute('open'); ui.certificate.hidden = true; ui.toggle.focus(); }
  }
  $('certificate-close').addEventListener('click', closeCertificateSetup);
  ui.certificate.addEventListener('close', () => { ui.certificate.hidden = true; ui.toggle.focus(); });
  window.addEventListener('pagehide', () => {
    if (state.id && navigator.sendBeacon) navigator.sendBeacon(`${apiRoot}/${encodeURIComponent(state.id)}/leave`, new Blob(['{}'], { type: 'application/json' }));
    stopMic('Microphone stopped');
  });
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible' && state.active) acquireWakeLock(); });
  refreshReverb(); setLinks(); refreshInfo(); setInterval(refreshInfo, 5000);
})();
