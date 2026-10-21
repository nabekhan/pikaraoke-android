const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { JSDOM, VirtualConsole } = require('jsdom');
const generated = path.join(__dirname, '../../../../app/build/generated/python/pikaraoke');
const templates = path.join(generated, 'templates');
const assets = path.join(generated, 'static');
const tick = () => new Promise(resolve => setImmediate(resolve));
async function settle() { for (let i=0;i<12;i++) await tick(); }
function power(c,on) {
  c.w.document.getElementById('mic-toggle').dispatchEvent(new c.w.KeyboardEvent('keydown',{key:on?'End':'Home',bubbles:true,cancelable:true}));
}
function slide(c,from,to,cancel=false) {
  const slider=c.w.document.getElementById('mic-toggle');
  for (const [type,y] of [['pointerdown',from],['pointermove',to],[cancel?'pointercancel':'pointerup',to]]) {
    const event=new c.w.MouseEvent(type,{clientY:y,button:0,bubbles:true,cancelable:true});
    Object.defineProperty(event,'pointerId',{value:1}); slider.dispatchEvent(event);
  }
}

function client(options={}) {
  let navigations=0, fullscreenRequests=0, fullscreenExits=0, wakeRequests=0, wakeReleases=0;
  const virtualConsole=new VirtualConsole();
  virtualConsole.on('jsdomError',error=>{if(/navigation/.test(error.message)) navigations++;else throw error;});
  const dom = new JSDOM(fs.readFileSync(path.join(templates,'phone-mic.html'),'utf8').replace(/{{ mic_config\|tojson }}/, '{}'), {
    url:options.insecure?'http://tv.test:8080/mic':'https://tv.test/mic', runScripts:'outside-only', pretendToBeVisual:true,virtualConsole
  });
  const w=dom.window, calls=[], sent=[];
  let captures=0, stopped=0, audio, channel, worklet, resolveCapture,resolveProbe;
  Object.defineProperty(w,'isSecureContext',{value:!options.insecure});
  if(options.agent) Object.defineProperty(w.navigator,'userAgent',{value:options.agent});
  if(options.standalone) Object.defineProperty(w.navigator,'standalone',{value:true});
  if(options.fullscreen) {
    w.document.documentElement.requestFullscreen=async()=>{
      fullscreenRequests++;
      if(options.rejectFullscreen) throw new Error('Fullscreen denied');
      w.document.fullscreenElement=w.document.documentElement;
      w.document.dispatchEvent(new w.Event('fullscreenchange'));
    };
    w.document.exitFullscreen=async()=>{
      fullscreenExits++;w.document.fullscreenElement=null;
      w.document.dispatchEvent(new w.Event('fullscreenchange'));
    };
  }
  w.phoneMicConfig={secure_url:'https://tv.test:8444/mic',ca_url:'/mic/ca.crt',asset_version:'content-hash'};
  const stream={getTracks:()=>[track],getAudioTracks:()=>[track]};
  const track={stop(){stopped++;},onended:null};
  w.navigator.mediaDevices={getUserMedia:()=>{
    captures++;
    return options.pendingCapture ? new Promise(resolve=>{resolveCapture=()=>resolve(stream);}) : Promise.resolve(stream);
  }};
  w.fetch=async (url, config={})=>{
    calls.push([url,config]);
    if(url===w.phoneMicConfig.secure_url) {
      if(options.pendingProbe) return new Promise(resolve=>{resolveProbe=()=>resolve({type:'opaque'});});
      if(options.trusted) return {type:'opaque'};
      throw new TypeError('Untrusted certificate');
    }
    let value={ok:true}, status=200;
    const max=options.max ?? 2;
    if(url==='/api/phone-mics' && !config.method) value={max,active:options.active || (options.full ? Array.from({length:max},(_,index)=>({slot:index+1,name:'Singer',connected:true})) : []),now_playing:{title:'A song'}};
    else if(url==='/api/phone-mics' && config.method==='POST') {value={id:'token',slot:1,max};status=201;}
    else if(url.endsWith('/offer')) {value={type:'answer',sdp:'answer'};if(options.failOffer){status=503;value={error:'Could not connect'};}}
    return {ok:status<400,status,json:async()=>value};
  };
  const node=()=>({connect(other){return other;},gain:{value:0}});
  w.AudioContext=class {
    constructor(){audio=this;this.state='running';this.sampleRate=48000;this.currentTime=0;this.audioWorklet={addModule:async url=>{assert.equal(url,'/static/phone-mic-worklet.js?v=content-hash');}};this.destination=node();}
    async resume(){} async close(){this.state='closed';}
    createMediaStreamSource(){return node();} createGain(){return node();}
  };
  w.AudioWorkletNode=class {
    constructor(){worklet=this;this.port={onmessage:null};} connect(other){return other;}
  };
  w.RTCPeerConnection=class {
    constructor(){this.iceGatheringState='complete';}
    createDataChannel(label,init){
      assert.equal(label,'audio');assert.equal(init.ordered,false);assert.equal(init.maxRetransmits,0);
      channel={readyState:'connecting',bufferedAmount:0,send(packet){sent.push(packet);},close(){this.readyState='closed';this.onclose?.();}};
      return channel;
    }
    async createOffer(){return {type:'offer',sdp:'m=application 9 UDP/DTLS/SCTP webrtc-datachannel'};}
    async setLocalDescription(description){this.localDescription=description;}
    async setRemoteDescription(){}
    close(){}
  };
  w.eval(fs.readFileSync(path.join(assets,'phone-mic.js'),'utf8'));
  w.navigator.wakeLock={request:async()=>{wakeRequests++;return {release:async()=>{wakeReleases++;}};}};
  return {w,calls,sent,get captures(){return captures;},get stopped(){return stopped;},get navigations(){return navigations;},get fullscreenRequests(){return fullscreenRequests;},get fullscreenExits(){return fullscreenExits;},get wakeRequests(){return wakeRequests;},get wakeReleases(){return wakeReleases;},get audio(){return audio;},get worklet(){return worklet;},get channel(){return channel;},resolveCapture:()=>resolveCapture(),resolveProbe:()=>resolveProbe(),close:()=>dom.window.close()};
}

(async()=>{
  const frames=[];let Processor;
  const workletScope={sampleRate:48000,currentTime:0,
    AudioWorkletProcessor:class {constructor(){this.port={postMessage:message=>frames.push(message)};}},
    registerProcessor:(name,processor)=>{Processor=processor;}};
  vm.runInNewContext(fs.readFileSync(path.join(assets,'phone-mic-worklet.js'),'utf8'),workletScope);
  const processor=new Processor(), silentOutput=new Float32Array(128).fill(1);
  processor.process([[new Float32Array(128).fill(.5)]],[[silentOutput]]);
  assert.equal(frames.length,1);workletScope.currentTime=128/48000;
  processor.process([[new Float32Array(128).fill(.5)]],[[silentOutput]]);
  assert.equal(frames.length,2);assert.equal(frames[0].samples.length,128);
  assert.equal(frames[0].rms,.5);assert.ok(silentOutput.every(value=>value===0),'phone must not play its own microphone');
  let c=client();await settle();
  assert.equal(c.w.document.getElementById('slot-list').children.length,2,'two mic bars by default');
  assert.equal(c.w.document.getElementById('gain').value,'30','TV mic starts at 30% volume');
  c.w.document.cookie=`user=${encodeURIComponent('Zoë & Sam')}; path=/`;
  c.w.document.getElementById('mic-toggle').click();slide(c,200,200);await settle();
  assert.equal(c.captures,0,'a tap must not enable the microphone');
  slide(c,200,170);await settle();assert.equal(c.captures,0,'a partial slide snaps back');
  slide(c,200,100,true);await settle();assert.equal(c.captures,0,'an interrupted slide must not enable capture');
  slide(c,200,100);await settle();
  const reservation=c.calls.find(([url,config])=>url==='/api/phone-mics'&&config.method==='POST');
  assert.equal(JSON.parse(reservation[1].body).name,'Zoë & Sam','reuse the existing PiKaraoke name');
  assert.equal(c.w.document.getElementById('mic-toggle').classList.contains('live'),false,'must not show live before data channel opens');
  c.channel.readyState='open';c.channel.onopen();await settle();
  assert.equal(c.w.document.getElementById('mic-toggle').classList.contains('live'),true);
  const initialControls=c.calls.filter(([url])=>url.endsWith('/controls')).at(-1);
  assert.equal(JSON.parse(initialControls[1].body).gain,.6,'30% keeps the existing volume-to-gain scale');
  const capture={data:{samples:new Float32Array(256).fill(.5),rms:.5,time:0}};
  c.worklet.port.onmessage(capture);
  assert.equal(c.sent.length,1);
  let packet=new DataView(c.sent[0]);
  assert.equal(packet.byteLength,528);assert.equal(packet.getUint16(10,true),256);
  assert.equal(packet.getUint8(12),3);assert.equal(packet.getUint8(13),16);
  assert.equal(packet.getInt16(16,true),16383);
  c.channel.bufferedAmount=1100;c.worklet.port.onmessage(capture);assert.equal(c.sent.length,1,'backpressure drops stale audio');
  c.channel.bufferedAmount=0;c.audio.currentTime=1;c.worklet.port.onmessage(capture);assert.equal(c.sent.length,1,'main-thread backlog is dropped');
  c.w.document.getElementById('volume-toggle').click();
  assert.equal(c.w.document.getElementById('volume-panel').hidden,false);
  const gain=c.w.document.getElementById('gain');gain.value=45;gain.dispatchEvent(new c.w.Event('input'));await settle();
  c.w.document.getElementById('reverb').click();
  assert.equal(c.w.document.getElementById('volume-panel').hidden,true,'only one adjustment opens at once');
  c.w.document.querySelector('[data-reverb="2"]').click();await settle();
  const controls=c.calls.filter(([url])=>url.endsWith('/controls')).at(-1);
  assert.deepEqual(JSON.parse(controls[1].body),{gain:.9,muted:false,reverb:2});
  assert.equal(c.w.document.getElementById('reverb-panel').hidden,true);
  for (const [percent, expected] of [[0,0],[50,1],[100,2]]) {
    gain.value=percent;gain.dispatchEvent(new c.w.Event('input'));await settle();
    const request=c.calls.filter(([url])=>url.endsWith('/controls')).at(-1);
    assert.equal(JSON.parse(request[1].body).gain,expected,'50% is the former 100% gain');
  }

  c.w.document.getElementById('mic-toggle').click();await settle();assert.equal(c.stopped,0,'a tap must not disconnect a live microphone');
  slide(c,100,200);await settle();
  assert.equal(c.stopped,1);assert.equal(c.audio.state,'closed');
  c.audio.currentTime=0;c.worklet.port.onmessage(capture);assert.equal(c.sent.length,1,'sliding off stops transmission');
  assert.ok(c.calls.some(([url,config])=>url==='/api/phone-mics/token' && config.method==='DELETE'),'stop releases slot');
  c.close();

  c=client({failOffer:true});await settle();power(c,true);await settle();
  assert.equal(c.stopped,1,'failed negotiation stops capture');
  assert.ok(c.calls.some(([url,config])=>url.endsWith('/token')&&config.method==='DELETE'),'failed negotiation releases slot');
  assert.equal(c.w.document.getElementById('mic-toggle').classList.contains('live'),false);c.close();

  c=client({pendingCapture:true});await settle();power(c,true);await settle();
  c.w.dispatchEvent(new c.w.Event('pagehide'));await settle();c.resolveCapture();await settle();
  assert.equal(c.stopped,1,'permission granted after leaving must not leave capture running');
  assert.ok(!c.calls.some(([url,config])=>url==='/api/phone-mics'&&config.method==='POST'),'cancelled start must not reserve a slot');c.close();

  c=client({pendingCapture:true});await settle();power(c,true);await settle();power(c,false);await settle();c.resolveCapture();await settle();
  assert.equal(c.stopped,1,'sliding off during a permission request cancels late capture');
  assert.ok(!c.calls.some(([url,config])=>url==='/api/phone-mics'&&config.method==='POST'));c.close();

  c=client({full:true});await settle();power(c,true);await settle();
  assert.equal(c.captures,0,'full room must not acquire microphone');
  assert.match(c.w.document.getElementById('mic-status').textContent,/All mics/);c.close();

  c=client({max:4});await settle();
  assert.equal(c.w.document.getElementById('slot-list').children.length,4);c.close();
  c=client({max:1,active:[{slot:3,name:'Singer',connected:true}]});await settle();
  assert.equal(c.w.document.getElementById('slot-list').children.length,3,'keep an existing higher slot visible after lowering the limit');
  power(c,true);await settle();assert.equal(c.captures,0,'lowered limit blocks new capture without removing existing singers');c.close();

  c=client({insecure:true,agent:'iPhone'});await settle();
  assert.equal(c.w.document.getElementById('certificate-panel').hidden,true,'HTTP page remains usable until mic activation');
  power(c,true);await settle();
  assert.equal(c.captures,0,'HTTP mic activation must not request capture');
  assert.equal(c.w.document.getElementById('certificate-panel').hidden,false,'untrusted HTTPS shows brief setup');
  assert.match(c.w.document.getElementById('certificate-instructions').textContent,/Profile Downloaded.*Certificate Trust Settings/);
  assert.equal(c.w.document.getElementById('secure-link').href,'https://tv.test:8444/mic');
  c.w.document.getElementById('certificate-close').click();assert.equal(c.w.document.getElementById('certificate-panel').hidden,true);c.close();

  c=client({insecure:true,trusted:true});await settle();power(c,true);await settle();
  assert.equal(c.navigations,1,'a trusted HTTPS endpoint redirects without setup');
  assert.equal(c.w.document.getElementById('certificate-panel').hidden,true);assert.equal(c.captures,0);c.close();

  c=client({insecure:true,pendingProbe:true});await settle();power(c,true);await settle();power(c,false);await settle();c.resolveProbe();await settle();
  assert.equal(c.navigations,0,'cancelling the slide prevents a late HTTPS redirect');
  assert.equal(c.w.document.getElementById('certificate-panel').hidden,true);c.close();

  c=client({agent:'Android',fullscreen:true});await settle();
  const fullscreen=c.w.document.getElementById('fullscreen-toggle');
  assert.equal(fullscreen.hidden,false);
  fullscreen.click();await settle();assert.equal(c.fullscreenRequests,1);
  assert.equal(fullscreen.getAttribute('aria-pressed'),'true');
  fullscreen.click();await settle();assert.equal(c.fullscreenExits,1);
  power(c,true);await settle();assert.equal(c.fullscreenRequests,2,'starting the Android mic requests full screen within the gesture');
  c.channel.readyState='open';c.channel.onopen();await settle();
  const lock=c.w.document.getElementById('lock-toggle');
  c.w.document.getElementById('volume-toggle').click();
  lock.click();await settle();
  assert.equal(lock.getAttribute('aria-pressed'),'true');
  assert.equal(c.w.document.getElementById('lock-hint').hidden,false);
  assert.equal(c.w.document.getElementById('volume-panel').hidden,true,'locking closes adjustments');
  assert.ok(c.w.document.querySelector('.mic-console').hasAttribute('inert'));
  const beforeControls=c.calls.filter(([url])=>url.endsWith('/controls')).length;
  slide(c,100,200);power(c,false);
  c.w.document.getElementById('volume-toggle').click();
  c.w.document.getElementById('gain').dispatchEvent(new c.w.Event('input',{bubbles:true}));
  c.w.document.querySelector('[data-reverb="2"]').click();
  c.w.document.getElementById('back-link').click();fullscreen.click();await settle();
  assert.equal(c.stopped,0,'locked sliders and keys must not disconnect a live microphone');
  assert.equal(c.navigations,0,'locked back button must not leave the microphone');
  assert.equal(c.fullscreenExits,1,'locked full-screen button must not exit');
  assert.equal(c.calls.filter(([url])=>url.endsWith('/controls')).length,beforeControls,'locked controls cannot change audio');
  assert.equal(c.w.document.getElementById('volume-panel').hidden,true);
  function lockPointer(type) {
    const event=new c.w.MouseEvent(type,{button:0,clientX:40,clientY:40,bubbles:true,cancelable:true});
    Object.defineProperty(event,'pointerId',{value:2});lock.dispatchEvent(event);
  }
  lockPointer('pointerdown');lockPointer('pointerup');lock.click();
  assert.equal(lock.getAttribute('aria-pressed'),'true','a short tap must not unlock');
  lockPointer('pointerdown');lockPointer('pointercancel');
  await new Promise(resolve=>setTimeout(resolve,1450));
  assert.equal(lock.getAttribute('aria-pressed'),'true','an interrupted hold must not unlock later');
  lockPointer('pointerdown');await new Promise(resolve=>setTimeout(resolve,1450));
  lockPointer('pointerup');lock.click();await settle();
  assert.equal(lock.getAttribute('aria-pressed'),'false','holding unlocks without the following click relocking');
  assert.ok(!c.w.document.querySelector('.mic-console').hasAttribute('inert'));
  assert.equal(c.stopped,0,'locking and unlocking keep the microphone live');
  lock.click();lock.dispatchEvent(new c.w.KeyboardEvent('keydown',{key:' ',bubbles:true,cancelable:true}));
  await new Promise(resolve=>setTimeout(resolve,1450));
  lock.dispatchEvent(new c.w.KeyboardEvent('keyup',{key:' ',bubbles:true,cancelable:true}));
  assert.equal(lock.getAttribute('aria-pressed'),'false','keyboard users can hold Space to unlock');
  power(c,false);await settle();assert.equal(c.stopped,1);c.close();

  c=client({agent:'iPhone',fullscreen:true});await settle();
  assert.equal(c.w.document.getElementById('fullscreen-toggle').hidden,true,'full screen is Android only');
  power(c,true);await settle();assert.equal(c.fullscreenRequests,0,'iOS mic does not request full screen');
  c.channel.readyState='open';c.channel.onopen();await settle();
  assert.equal(c.wakeRequests,1,'an active mic requests a screen wake lock');
  Object.defineProperty(c.w.document,'visibilityState',{value:'hidden',configurable:true});c.w.document.dispatchEvent(new c.w.Event('visibilitychange'));await settle();
  assert.equal(c.wakeReleases,1,'hidden pages release the wake lock');
  Object.defineProperty(c.w.document,'visibilityState',{value:'visible',configurable:true});c.w.document.dispatchEvent(new c.w.Event('visibilitychange'));await settle();
  assert.equal(c.wakeRequests,2,'visible active pages reacquire the wake lock');
  c.w.dispatchEvent(new c.w.Event('pagehide'));await settle();assert.ok(c.wakeReleases>=2,'stopping releases the wake lock');c.close();

  c=client({agent:'Android',fullscreen:true,rejectFullscreen:true});await settle();
  c.w.document.getElementById('fullscreen-toggle').click();await settle();
  assert.match(c.w.document.getElementById('mic-status').textContent,/Could not enter full screen/);
  power(c,true);await settle();assert.equal(c.captures,1,'full-screen refusal must not prevent microphone use');
  c.channel.readyState='open';c.channel.onopen();await settle();
  c.w.dispatchEvent(new c.w.Event('pagehide'));await settle();c.close();

  c=client({agent:'Android',standalone:true,fullscreen:true});await settle();
  assert.equal(c.w.document.getElementById('fullscreen-toggle').hidden,true,'an installed web app needs no full-screen toggle');c.close();
  console.log('Browser mic: deliberate slide, controls, Android full screen, hold-to-unlock, HTTPS onboarding/redirect, PCM framing, backpressure, cleanup and configurable capacity passed');
})().catch(error=>{console.error(error);process.exit(1);});
