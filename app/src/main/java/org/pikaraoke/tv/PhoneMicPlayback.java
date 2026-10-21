package org.pikaraoke.tv;

import android.media.*;
import android.util.Log;

/** Native low-latency output, retaining AudioTrack on unsupported devices. */
final class PhoneMicPlayback {
    private AudioTrack legacy;
    private long nativeStream;
    private final long[] info = new long[9];
    private long lastInfo;
    private double latencyMillis = -1;
    private static final boolean NATIVE_AVAILABLE;
    static {
        boolean loaded;
        try { System.loadLibrary("pikaraoke_phone_audio"); loaded = true; }
        catch (UnsatisfiedLinkError error) {
            Log.w("PiKaraokePhoneMic", "Native phone audio unavailable; using AudioTrack", error);
            loaded = false;
        }
        NATIVE_AVAILABLE = loaded;
    }

    private PhoneMicPlayback(AudioTrack track) { legacy = track; }

    static PhoneMicPlayback open(int burst) {
        int minimum = AudioTrack.getMinBufferSize(48000, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT);
        AudioTrack track = new AudioTrack.Builder().setAudioAttributes(new AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build())
            .setAudioFormat(new AudioFormat.Builder().setSampleRate(48000).setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                .setEncoding(AudioFormat.ENCODING_PCM_16BIT).build())
            .setTransferMode(AudioTrack.MODE_STREAM).setBufferSizeInBytes(Math.max(minimum, 1920))
            .setPerformanceMode(AudioTrack.PERFORMANCE_MODE_LOW_LATENCY).build();
        PhoneMicPlayback output = new PhoneMicPlayback(track);
        try {
            if (track.getState() != AudioTrack.STATE_INITIALIZED) throw new IllegalStateException("Audio output unavailable");
            track.setBufferSizeInFrames(Math.min(track.getBufferCapacityInFrames(), burst * 2));
            track.play();
            if (NATIVE_AVAILABLE) {
                // AAudio's default device can be the Streamer's silent internal
                // speaker. Discover the selected media route, then bind to it.
                short[] silence = new short[track.getBufferSizeInFrames()];
                track.write(silence, 0, silence.length, AudioTrack.WRITE_NON_BLOCKING);
                AudioDeviceInfo device = track.getRoutedDevice();
                for (int attempt = 0; device == null && attempt < 20; attempt++) {
                    java.util.concurrent.locks.LockSupport.parkNanos(5_000_000L);
                    device = track.getRoutedDevice();
                }
                if (device != null) output.nativeStream = nativeOpen(device.getId());
                if (output.nativeStream != 0) { track.release(); output.legacy = null; output.refresh(); }
            }
            Log.i("PiKaraokePhoneMic", output.backend() + " output buffer: " + output.bufferFrames() + " frames at 48000 Hz");
            return output;
        } catch (RuntimeException error) { output.close(); throw error; }
    }

    synchronized int write(short[] data, int offset, int count) {
        if (legacy != null) return legacy.write(data, offset, count, AudioTrack.WRITE_NON_BLOCKING);
        if (nativeStream == 0) return AudioTrack.ERROR_DEAD_OBJECT;
        int result = nativeWrite(nativeStream, data, offset, count);
        if (result == -899 || result == -895) { // AAudio DISCONNECTED / INVALID_STATE.
            Log.w("PiKaraokePhoneMic", "AAudio output needs reopening: " + result);
            return AudioTrack.ERROR_DEAD_OBJECT;
        }
        return result;
    }
    private void refresh() {
        if (nativeStream == 0 || System.nanoTime() - lastInfo < 50_000_000L) return;
        nativeInfo(nativeStream, info); lastInfo = System.nanoTime();
        if (info[8] == 0) {
            double estimate = (info[5] - info[6]) / 48.0 - (lastInfo - info[7]) / 1e6;
            latencyMillis = Double.isFinite(estimate) ? Math.max(0, estimate) : -1;
        }
    }
    synchronized long playbackFrames() { refresh(); return legacy != null ? Integer.toUnsignedLong(legacy.getPlaybackHeadPosition()) : info[0]; }
    synchronized int bufferFrames() { refresh(); return legacy != null ? legacy.getBufferSizeInFrames() : (int)info[1]; }
    synchronized int capacityFrames() { refresh(); return legacy != null ? legacy.getBufferCapacityInFrames() : (int)info[2]; }
    synchronized int underruns() { refresh(); return legacy != null ? legacy.getUnderrunCount() : Math.max(0, (int)info[3]); }
    synchronized int burstFrames(int fallback) { refresh(); return nativeStream != 0 ? (int)info[4] : fallback; }
    synchronized double latencyMillis() { refresh(); return latencyMillis; }
    synchronized String backend() { return nativeStream != 0 ? "AAudio" : "AudioTrack"; }
    synchronized void setBufferFrames(int frames) {
        if (legacy != null) legacy.setBufferSizeInFrames(frames);
        else if (nativeStream != 0) { nativeSetBuffer(nativeStream, frames); lastInfo = 0; }
    }
    synchronized void pause() {
        if (legacy != null) legacy.pause(); else if (nativeStream != 0) nativePause(nativeStream);
    }
    synchronized void close() {
        if (legacy != null) { legacy.release(); legacy = null; }
        if (nativeStream != 0) { nativeClose(nativeStream); nativeStream = 0; }
    }

    private static native long nativeOpen(int device);
    private static native int nativeWrite(long stream, short[] data, int offset, int count);
    private static native void nativeInfo(long stream, long[] result);
    private static native void nativeSetBuffer(long stream, int frames);
    private static native void nativePause(long stream);
    private static native void nativeClose(long stream);
}
