class PhoneMicProcessor extends AudioWorkletProcessor {
  constructor() { super(); this.samples = []; this.packetSize = 256; }
  process(inputs, outputs) {
    const input = inputs[0];
    const channel = input && input[0];
    if (!channel) return true;
    for (let i = 0; i < channel.length; i += 1) {
      this.samples.push(channel[i]);
      if (this.samples.length === this.packetSize) {
        const packet = new Float32Array(this.samples);
        let sum = 0;
        for (let j = 0; j < packet.length; j += 1) sum += packet[j] * packet[j];
        this.port.postMessage({ samples: packet, rms: Math.sqrt(sum / packet.length), time: currentTime + (i + 1) / sampleRate }, [packet.buffer]);
        this.samples = [];
      }
    }
    const output = outputs[0];
    if (output) for (const channelOut of output) channelOut.fill(0);
    return true;
  }
}
registerProcessor('phone-mic-processor', PhoneMicProcessor);
