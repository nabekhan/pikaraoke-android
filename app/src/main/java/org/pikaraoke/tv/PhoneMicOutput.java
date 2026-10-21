package org.pikaraoke.tv;

/** Final output limiter: preserve normal gain, compress peaks without ducking whole blocks. */
public final class PhoneMicOutput {
    private PhoneMicOutput() { }
    public static void encode(float[] input, short[] output) {
        for (int i=0;i<input.length;i++) {
            float sample = Float.isFinite(input[i]) ? input[i] : 0;
            float magnitude = Math.abs(sample);
            if (magnitude > .9f) {
                float excess = magnitude - .9f;
                sample = Math.copySign(.9f + .1f * excess / (.1f + excess), sample);
            }
            output[i] = (short)(sample * 32767);
        }
    }
}
