const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const sourcePath = path.join(__dirname, '../../../build/generated/python/pikaraoke/static/js/splash.js');
const source = fs.readFileSync(sourcePath, 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

function makeJQuery(window) {
  return (selector) => {
    if (typeof selector === 'function') return { ready: true };
    const nodes = typeof selector === 'string'
      ? [...window.document.querySelectorAll(selector)]
      : selector ? [selector] : [];
    const chain = {
      0: nodes[0], length: nodes.length,
      hide() { nodes.forEach(node => { node.hidden = true; }); return chain; },
      show() { nodes.forEach(node => { node.hidden = false; }); return chain; },
      fadeIn() { return chain.show(); }, fadeOut() { return chain.hide(); },
      addClass() { return chain; }, removeClass() { return chain; }, toggle() { return chain; },
      stop() { return chain; }, animate(_, __, done) { if (typeof done === 'function') done(); return chain; },
      click() { return chain; }, on() { return chain; },
      text(value) { if (value === undefined) return nodes[0]?.textContent; nodes.forEach(node => { node.textContent = value; }); return chain; },
      html(value) { if (value === undefined) return nodes[0]?.innerHTML; nodes.forEach(node => { node.innerHTML = value; }); return chain; },
      attr(name, value) { if (value === undefined) return nodes[0]?.getAttribute(name); nodes.forEach(node => node.setAttribute(name, value)); return chain; },
    };
    return chain;
  };
}

function client() {
  const dom = new JSDOM(`<!doctype html><body>
    <div id="video-container"><video id="video"><source id="video-source"></video></div>
    <div id="now-playing"></div><div id="up-next"></div><div id="duration"></div>
    <div id="now-playing-song"></div><div id="now-playing-singer"></div>
    <div id="up-next-song"></div><div id="up-next-singer"></div>
    <div id="session-name"></div><div id="bg-video-container"></div>
    <audio id="background-music"></audio><video id="bg-video"></video>
  </body>`, { url: 'https://tv.test/splash', runScripts: 'outside-only' });
  const w = dom.window;
  const video = w.document.getElementById('video');
  const sourceEl = w.document.getElementById('video-source');
  const log = { loads: [], pauses: 0, plays: 0, setters: [], hls: [], emitted: [] };
  const timers = [];
  let directSrc = '';
  let nativeHls = true;
  let rejectPlay = false;
  Object.defineProperties(video, {
    src: { configurable: true, get: () => directSrc, set: value => { directSrc = new URL(value, w.location.href).href; log.setters.push(directSrc); } },
    currentSrc: { configurable: true, get: () => directSrc },
    paused: { configurable: true, writable: true, value: true },
    ended: { configurable: true, writable: true, value: false },
    readyState: { configurable: true, writable: true, value: 4 },
    currentTime: { configurable: true, writable: true, value: 0 },
    volume: { configurable: true, writable: true, value: 1 },
    error: { configurable: true, writable: true, value: null },
  });
  const removeVideoAttribute = video.removeAttribute.bind(video);
  video.removeAttribute = name => { if (name === 'src') directSrc = ''; removeVideoAttribute(name); };
  for (const id of ['background-music', 'bg-video']) {
    const media = w.document.getElementById(id);
    media.pause = () => {};
    media.play = () => Promise.resolve();
    media.load = () => {};
  }
  video.canPlayType = () => nativeHls ? 'maybe' : '';
  video.pause = () => { log.pauses += 1; video.paused = true; };
  video.load = () => {
    log.loads.push({ direct: directSrc, child: sourceEl.getAttribute('src') });
    video.currentTime = 0; video.ended = false; video.error = null;
  };
  video.play = () => {
    log.plays += 1;
    if (rejectPlay) { rejectPlay = false; return Promise.reject(new Error('blocked')); }
    video.paused = false;
    video.dispatchEvent(new w.Event('play'));
    if (video.readyState > 2) video.dispatchEvent(new w.Event('playing'));
    return Promise.resolve();
  };
  const Hls = class {
    constructor(options) { this.options = options; this.destroyed = false; log.hls.push(this); }
    loadSource(url) { this.source = url; }
    attachMedia(media) { this.media = media; }
    destroy() { this.destroyed = true; }
  };
  const socket = { connected: false, on() {}, emit(...args) { log.emitted.push(args); }, connect() {} };
  w.$ = makeJQuery(w);
  w.console = { log() {}, error() {} };
  w.io = () => socket;
  w.Hls = Hls;
  w.PikaraokeConfig = { bgVideoChoices: [], screensaverTimeout: 0, hideOverlay: false, hideSessionName: false, disableScore: true, splashScale: 1, showSplashClock: false, bgMusicVolume: 0 };
  w.pikaraokeConfig = { basePath: '', socketioPath: '/socket.io' };
  w.SubtitlesOctopus = class {};
  w.getSemitonesLabel = () => '';
  w.setInterval = () => 1;
  w.setTimeout = (fn, delay) => { timers.push({ fn, delay }); return timers.length; };
  w.clearTimeout = () => {};
  const bridge = `\nwindow.__playbackTest = { handleNowPlayingUpdate, stopVideoPlayback, setupVideoPlayer, setMaster: value => { isMaster = value; }, state: () => ({ currentVideoUrl, currentPlaybackId, hlsInstance, videoSourceGeneration }) };`;
  w.eval(`${source}${bridge}`);
  w.__playbackTest.setupVideoPlayer();
  const flush = async (delay) => {
    const pending = timers.filter(timer => timer.delay === delay);
    for (const timer of pending) timer.fn();
    for (const timer of pending) timers.splice(timers.indexOf(timer), 1);
    await tick();
  };
  return { w, video, sourceEl, log, timers, setNativeHls: value => { nativeHls = value; }, rejectNextPlay: () => { rejectPlay = true; }, flush, close: () => dom.window.close() };
}

const song = (url, playbackId) => ({ now_playing: 'Song', now_playing_url: url, playback_id: playbackId, volume: .8 });

(async () => {
  const c = client();
  const first = 'https://media.test/one.m3u8';
  const second = 'https://media.test/two.m3u8';
  c.w.__playbackTest.handleNowPlayingUpdate(song(first, 'one'));
  assert.equal(c.video.src, first, 'first native HLS source uses the video element directly');
  assert.equal(c.sourceEl.hasAttribute('src'), false, 'child source stays detached');
  c.w.__playbackTest.handleNowPlayingUpdate(song(second, 'two'));
  assert.equal(c.video.src, second, 'consecutive native HLS replaces the direct source');
  assert.equal(c.sourceEl.hasAttribute('src'), false, 'consecutive native HLS leaves no stale child source');
  assert.deepEqual(c.log.loads.at(-2), { direct: '', child: null }, 'handoff commits an empty source before the successor');

  c.setNativeHls(false);
  const hlsSong = 'https://media.test/three.m3u8';
  const loadsBeforeHls = c.log.loads.length;
  c.w.__playbackTest.handleNowPlayingUpdate(song(hlsSong, 'three'));
  const hls = c.log.hls.at(-1);
  assert.equal(hls.source, hlsSong, 'hls.js receives its source');
  assert.equal(c.log.loads.length, loadsBeforeHls + 1, 'hls.js does not get an extra direct video.load');
  assert.equal(c.video.src, '', 'hls.js starts after an empty direct source');
  c.setNativeHls(true);
  const nativeAfterHls = 'https://media.test/four.m3u8';
  c.w.__playbackTest.handleNowPlayingUpdate(song(nativeAfterHls, 'four'));
  assert.equal(hls.destroyed, true, 'native HLS destroys the previous hls.js instance');
  assert.equal(c.video.src, nativeAfterHls, 'hls.js-to-native assigns only the new native source');

  const progressive = 'https://media.test/five.mp4';
  c.w.__playbackTest.handleNowPlayingUpdate(song(progressive, 'five'));
  assert.equal(c.video.src, progressive, 'native HLS-to-progressive assigns the direct source');
  assert.equal(c.sourceEl.hasAttribute('src'), false, 'progressive mode has no competing source child');
  c.w.__playbackTest.stopVideoPlayback();
  assert.equal(c.video.src, '', 'stop removes the direct source');
  assert.equal(c.sourceEl.hasAttribute('src'), false, 'stop removes the child source');
  assert.equal(c.w.__playbackTest.state().hlsInstance, null, 'stop destroys any HLS owner');

  c.w.__playbackTest.setMaster(true);
  c.rejectNextPlay();
  const retryOld = 'https://media.test/retry-old.mp4';
  c.w.__playbackTest.handleNowPlayingUpdate(song(retryOld, 'retry-old'));
  await tick();
  assert.ok(c.timers.some(timer => timer.delay === 1000), 'failed play schedules one guarded retry');
  const playsBeforeSuccessor = c.log.plays;
  c.w.__playbackTest.handleNowPlayingUpdate(song('https://media.test/retry-new.mp4', 'retry-new'));
  await c.flush(1000);
  assert.equal(c.log.plays, playsBeforeSuccessor + 1, 'a delayed old retry cannot play the successor');
  await c.flush(1200);
  assert.ok(!c.log.emitted.some(([event, id]) => event === 'start_song' && id === 'retry-old'), 'a delayed old start report cannot name the successor');

  c.video.dispatchEvent(new c.w.Event('ended'));
  c.video.dispatchEvent(new c.w.Event('error'));
  assert.equal(c.video.src, 'https://media.test/retry-new.mp4', 'stale terminal events cannot stop a healthy successor');
  c.video.ended = true;
  c.video.dispatchEvent(new c.w.Event('ended'));
  assert.equal(c.video.src, '', 'a genuinely ended current source is released');
  assert.ok(c.log.emitted.some(([event, reason, id]) => event === 'end_song' && reason === 'complete' && id === 'retry-new'));

  c.w.__playbackTest.handleNowPlayingUpdate(song('https://media.test/broken.mp4', 'broken'));
  c.video.error = { code: 3 };
  c.video.dispatchEvent(new c.w.Event('error'));
  assert.equal(c.video.src, '', 'a direct video source error is handled on the video element');
  assert.ok(c.log.emitted.some(([event, reason, id]) => event === 'end_song' && reason === 'error while playing' && id === 'broken'));

  c.video.readyState = 1;
  c.w.__playbackTest.handleNowPlayingUpdate(song('https://media.test/slow.mp4', 'slow'));
  await c.flush(1200);
  assert.ok(!c.log.emitted.some(([event, id]) => event === 'start_song' && id === 'slow'), 'buffering alone is not a playback start');
  c.video.readyState = 4; c.video.currentTime = 2;
  c.video.dispatchEvent(new c.w.Event('playing'));
  await c.flush(1200);
  assert.ok(c.log.emitted.some(([event, id]) => event === 'start_song' && id === 'slow'), 'a slow source reports its start once playback begins');
  c.close();
  console.log('Splash playback: native/HLS/progressive handoff, stop, retry and start-report generations passed');
})().catch(error => { console.error(error); process.exit(1); });
