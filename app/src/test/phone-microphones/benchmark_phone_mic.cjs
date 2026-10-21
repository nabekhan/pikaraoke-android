/* Local transport benchmark; no microphone recording or audible output.
 * NODE_PATH=/path/to/node_modules CHROME_EXECUTABLE=/path/to/chrome node app/src/test/phone-microphones/benchmark_phone_mic.cjs
 * Optional dependencies: playwright-core and ws. Tests synthetic PCM, not physical-device latency.
 */
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { chromium } = require('playwright-core');
const { WebSocketServer } = require('ws');
const worklet = fs.readFileSync(path.join(__dirname, '../../../../app/build/generated/python/pikaraoke/static/phone-mic-worklet.js'), 'utf8');
const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost');
  res.setHeader('Cache-Control', 'no-store');
  if (url.pathname === '/worklet') {
    res.setHeader('Content-Type', 'text/javascript');
    res.end(worklet.replace(/this.packetSize = \d+/, `this.packetSize = ${url.searchParams.get('frames') === '128' ? 128 : 256}`));
  } else res.end('<!doctype html><title>Local PCM transport benchmark</title>');
});
const ws = new WebSocketServer({ server });
ws.on('connection', client => client.on('message', data => client.send(data)));
function listen() { return new Promise(resolve => server.listen(0, '127.0.0.1', resolve)); }
(async () => {
  await listen();
  const executablePath = process.env.CHROME_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  const options = {executablePath, headless:true, args:['--autoplay-policy=no-user-gesture-required','--disable-background-timer-throttling']};
  const browser = process.env.CHROME_PROFILE ? await chromium.launchPersistentContext(process.env.CHROME_PROFILE,options) : await chromium.launch(options);
  try {
    const page = await browser.newPage();
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    const result = await page.evaluate(async () => {
      const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
      function summary(values) {
        values.sort((a,b) => a-b);
        return {samples:values.length, median_ms:+values[Math.floor(values.length*.5)].toFixed(3),p95_ms:+values[Math.floor(values.length*.95)].toFixed(3)};
      }
      async function rtc(reliable) {
        const sender=new RTCPeerConnection(), receiver=new RTCPeerConnection();
        sender.onicecandidate=e=>{if(e.candidate)receiver.addIceCandidate(e.candidate);};
        receiver.onicecandidate=e=>{if(e.candidate)sender.addIceCandidate(e.candidate);};
        const channel=sender.createDataChannel('audio', reliable?{}:{ordered:false,maxRetransmits:0});
        const opened=new Promise(resolve=>{channel.onopen=resolve;});
        receiver.ondatachannel=e=>{e.channel.onmessage=message=>e.channel.send(message.data);};
        await sender.setLocalDescription(await sender.createOffer());
        await receiver.setRemoteDescription(sender.localDescription);
        await receiver.setLocalDescription(await receiver.createAnswer());
        await sender.setRemoteDescription(receiver.localDescription);
        await Promise.race([opened,delay(10000).then(()=>{throw Error('RTC open timed out');})]);
        return {channel,close:()=>{channel.close();sender.close();receiver.close();}};
      }
      const results=[];
      for (const transport of ['webrtc-unreliable','webrtc-reliable','websocket']) for (const frames of [256,128]) {
        let connection, channel;
        if(transport==='websocket') {
          channel=new WebSocket(location.origin.replace('http:','ws:')); channel.binaryType='arraybuffer';
          await new Promise(resolve=>{channel.onopen=resolve;});connection={channel,close:()=>channel.close()};
        } else {connection=await rtc(transport==='webrtc-reliable');channel=connection.channel;channel.binaryType='arraybuffer';}
        const ctx=new AudioContext({sampleRate:48000,latencyHint:'interactive'});await ctx.resume();
        await ctx.audioWorklet.addModule(`/worklet?frames=${frames}`);
        const oscillator=ctx.createOscillator();oscillator.frequency.value=997;
        const gain=ctx.createGain();gain.gain.value=.1;
        const capture=new AudioWorkletNode(ctx,'phone-mic-processor');
        oscillator.connect(gain).connect(capture).connect(ctx.destination);
        const times=[], captures=[], expected=new Map();let sent=0, corrupt=0;
        channel.onmessage=e=>{
          const packet=new DataView(e.data), seq=packet.getUint16(8,true), original=expected.get(seq);
          if(!original)return;
          const bytes=new Uint8Array(e.data);
          if(!original.bytes.every((byte,i)=>bytes[i]===byte))corrupt++;
          times.push((performance.now()-packet.getFloat64(0,true))/2);
          expected.delete(seq);
        };
        capture.port.onmessage=e=>{
          if(sent>=300)return;
          const samples=e.data.samples, bytes=new ArrayBuffer(16+2*samples.length), packet=new DataView(bytes);
          packet.setFloat64(0,performance.now(),true);packet.setUint16(8,sent,true);packet.setUint16(10,samples.length,true);
          packet.setUint8(12,3);packet.setUint8(13,16);packet.setUint8(14,1);packet.setUint8(15,1);
          samples.forEach((sample,i)=>packet.setInt16(16+2*i,Math.max(-1,Math.min(1,sample))*32767,true));
          expected.set(sent,{bytes:new Uint8Array(bytes)});sent++;
          captures.push(Math.max(0,(ctx.currentTime-e.data.time)*1000));
          channel.send(bytes);
        };
        oscillator.start();
        const deadline=performance.now()+10000;
        while((sent<300||expected.size)&&performance.now()<deadline)await delay(20);
        oscillator.stop();capture.disconnect();await ctx.close();connection.close();
        if(!times.length||corrupt)throw Error('Synthetic PCM transport failed');
        results.push({transport,frames,packetization_ms:+(frames/48).toFixed(3),estimated_one_way_loopback:summary(times.slice(20)),worklet_main_thread_age_ms:summary(captures.slice(20)),missing:expected.size,corrupt});
      }
      return {userAgent:navigator.userAgent,note:'Local synthetic PCM echo RTT/2. Excludes microphone hardware, Wi-Fi, TV receiver and output hardware. No packet loss injected.',results};
    });
    console.log(JSON.stringify(result,null,2));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>{ws.close();server.close();});
