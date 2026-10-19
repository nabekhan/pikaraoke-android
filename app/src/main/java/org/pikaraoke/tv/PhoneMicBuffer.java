package org.pikaraoke.tv;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.TreeMap;

/** Bounded PCM receiver. JackTrip DEFAULT header, mono PCM16, 44.1/48 kHz. */
public final class PhoneMicBuffer {
    private final TreeMap<Long, float[]> packets = new TreeMap<>();
    private float[] current;
    private int offset;
    private long latest = -1, expected = -1, lastPacket;
    private int queued, packetSize = 256, rate = 48000;
    private double phase;
    private boolean primed;
    private float sample;
    public volatile float gain = .65f;
    public volatile boolean muted;
    public volatile int reverb;
    private final float[] delay = new float[9600];
    private int delayIndex;
    public volatile long received, discarded, underruns;

    public synchronized boolean push(ByteBuffer source, long now) {
        ByteBuffer b = source.slice().order(ByteOrder.LITTLE_ENDIAN);
        if (b.remaining() < 18) return false;
        int seq = b.getShort(8) & 65535, count = b.getShort(10) & 65535;
        int code = b.get(12) & 255;
        if (count < 1 || count > 1024 || b.remaining() != 16 + count * 2
                || b.get(13) != 16 || (b.get(15) != 0 && b.get(15) != 1)
                || (code != 2 && code != 3)) return false;
        int nextRate = code == 2 ? 44100 : 48000;
        if (lastPacket != 0 && now - lastPacket > 250_000_000L) reset();
        if (nextRate != rate) { reset(); rate = nextRate; }
        long number = latest < 0 ? seq : latest + (short)(seq - (latest & 65535));
        if ((expected >= 0 && number < expected) || packets.containsKey(number)) {
            discarded++; return false;
        }
        if (latest >= 0 && number > latest + 64) reset();
        // A bounded queue is more valuable for monitoring than replaying old audio.
        if (queued + count > rate * .08) { resetAudio(); discarded++; }
        float[] pcm = new float[count];
        b.position(16);
        for (int i = 0; i < count; i++) pcm[i] = b.getShort() / 32768f;
        packets.put(number, pcm); queued += count;
        latest = Math.max(latest, number); lastPacket = now;
        packetSize = count; received++;
        return true;
    }

    public synchronized void controls(float volume, boolean mute, int effect) {
        gain = Math.max(0, Math.min(1, volume)); muted = mute;
        reverb = Math.max(0, Math.min(3, effect));
        if (mute) resetAudio();
    }

    public synchronized void mix(float[] output, long now) {
        if (muted || lastPacket == 0 || now - lastPacket > 250_000_000L) {
            resetAudio(); return;
        }
        int target = rate / 50; // 20 ms; not a claim of total latency.
        if (!primed) {
            if (queued < target) return;
            primed = true; expected = packets.firstKey();
        }
        // Gentle rate correction handles independent phone/output clocks.
        double correction = Math.max(-.003, Math.min(.003, (queued - target) / (double)rate * .1));
        double step = rate / 48000.0 * (1 + correction);
        for (int i = 0; i < output.length; i++) {
            phase += step;
            while (phase >= 1) { sample = nextSample(); phase -= 1; }
            float dry = sample * gain;
            float wet = delay[delayIndex];
            delay[delayIndex] = dry + wet * (reverb * .12f);
            delayIndex = (delayIndex + 1) % delay.length;
            output[i] += dry + wet * (reverb * .08f);
        }
    }

    private float nextSample() {
        if (current == null || offset == current.length) {
            current = packets.remove(expected++); offset = 0;
            if (current == null) {
                if (packets.isEmpty()) {
                    primed = false; expected = -1; underruns++; return 0;
                }
                // Conceal a missing packet without holding later audio indefinitely.
                current = new float[packetSize];
            } else queued -= current.length;
        }
        return current[offset++];
    }

    private void resetAudio() {
        packets.clear(); current = null; offset = 0; queued = 0;
        primed = false; expected = -1; phase = 0; sample = 0;
        java.util.Arrays.fill(delay, 0);
    }
    private void reset() { resetAudio(); latest = -1; }
    public synchronized int queuedFrames() { return queued + (current == null ? 0 : current.length - offset); }
}
