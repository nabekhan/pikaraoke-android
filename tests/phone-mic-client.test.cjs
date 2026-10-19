const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { JSDOM, VirtualConsole } = require('jsdom');
const assets = path.join(__dirname, '../app/src/main/assets');
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
  let navigations=0;
  const virtualConsole=new VirtualConsole();
  virtualConsole.on('jsdomError',error=>{if(/navigation/.test(error.message)) navigations++;else throw error;});
  const dom = new JSDOM(fs.readFileSync(path.join(assets,'phone-mic.html'),'utf8'), {
    url:options.insecure?'http://tv.test:8080/mic':'https://tv.test/mic', runScripts:'outside-only', pretendToBeVisual:true,virtualConsole
  });
  const w=dom.window, calls=[], sent=[];
  let captures=0, stopped=0, audio, channel, worklet, resolveCapture,resolveProbe;
  Object.defineProperty(w,'isSecureContext',{value:!options.insecure});
  if(options.agent) Object.defineProperty(w.navigator,'userAgent',{value:options.agent});
  w.phoneMicConfig={secure_url:'https://tv.test:8444/mic',ca_url:'/mic/ca.crt'};
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
    if(url==='/api/phone-mics' && !config.method) value={max:4,active:options.full ? [1,2,3,4].map(slot=>({slot,name:'Singer',connected:true})) : [],now_playing:{title:'A song'}};
    else if(url==='/api/phone-mics' && config.method==='POST') {value={id:'token',slot:1,max:4};status=201;}
    else if(url.endsWith('/offer')) {value={type:'answer',sdp:'answer'};if(options.failOffer){status=503;value={error:'Could not connect'};}}
    return {ok:status<400,status,json:async()=>value};
  };
  const node=()=>({connect(other){return other;},gain:{value:0}});
  w.AudioContext=class {
    constructor(){audio=this;this.state='running';this.sampleRate=48000;this.currentTime=0;this.audioWorklet={addModule:async()=>{}};this.destination=node();}
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
  return {w,calls,sent,get captures(){return captures;},get stopped(){return stopped;},get navigations(){return navigations;},get audio(){return audio;},get worklet(){return worklet;},get channel(){return channel;},resolveCapture:()=>resolveCapture(),resolveProbe:()=>resolveProbe(),close:()=>dom.window.close()};
}

(async()=>{
  const frames=[];let Processor;
  const workletScope={sampleRate:48000,currentTime:0,
    AudioWorkletProcessor:class {constructor(){this.port={postMessage:message=>frames.push(message)};}},
    registerProcessor:(name,processor)=>{Processor=processor;}};
  vm.runInNewContext(fs.readFileSync(path.join(assets,'phone-mic-worklet.js'),'utf8'),workletScope);
  const processor=new Processor(), silentOutput=new Float32Array(128).fill(1);
  processor.process([[new Float32Array(128).fill(.5)]],[[silentOutput]]);
  assert.equal(frames.length,0);workletScope.currentTime=128/48000;
  processor.process([[new Float32Array(128).fill(.5)]],[[silentOutput]]);
  assert.equal(frames.length,1);assert.equal(frames[0].samples.length,256);
  assert.equal(frames[0].rms,.5);assert.ok(silentOutput.every(value=>value===0),'phone must not play its own microphone');
  let c=client();await settle();
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
  const capture={data:{samples:new Float32Array(256).fill(.5),rms:.5,time:0}};
  c.worklet.port.onmessage(capture);
  assert.equal(c.sent.length,1);
  let packet=new DataView(c.sent[0]);
  assert.equal(packet.byteLength,528);assert.equal(packet.getUint16(10,true),256);
  assert.equal(packet.getUint8(12),3);assert.equal(packet.getUint8(13),16);
  assert.equal(packet.getInt16(16,true),16383);
  c.channel.bufferedAmount=5000;c.worklet.port.onmessage(capture);assert.equal(c.sent.length,1,'backpressure drops stale audio');
  c.channel.bufferedAmount=0;c.audio.currentTime=1;c.worklet.port.onmessage(capture);assert.equal(c.sent.length,1,'main-thread backlog is dropped');
  c.w.document.getElementById('volume-toggle').click();
  assert.equal(c.w.document.getElementById('volume-panel').hidden,false);
  const gain=c.w.document.getElementById('gain');gain.value=45;gain.dispatchEvent(new c.w.Event('input'));await settle();
  c.w.document.getElementById('reverb').click();
  assert.equal(c.w.document.getElementById('volume-panel').hidden,true,'only one adjustment opens at once');
  c.w.document.querySelector('[data-reverb="2"]').click();await settle();
  const controls=c.calls.filter(([url])=>url.endsWith('/controls')).at(-1);
  assert.deepEqual(JSON.parse(controls[1].body),{gain:.45,muted:false,reverb:2});
  assert.equal(c.w.document.getElementById('reverb-panel').hidden,true);
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
  assert.match(c.w.document.getElementById('mic-status').textContent,/four/);c.close();

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
  console.log('Browser mic: deliberate slide, controls, HTTPS onboarding/redirect, PCM framing, backpressure, cleanup and four-slot capacity passed');
})().catch(error=>{console.error(error);process.exit(1);});
