package org.pikaraoke.tv;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.media.*;
import android.media.audiofx.AcousticEchoCanceler;
import android.os.Process;
import android.util.Log;
import java.util.concurrent.ConcurrentHashMap;
import org.json.*;

/** Native local microphone loopback, including USB/audio-device routing. */
public final class AndroidAudio {
    private static final ConcurrentHashMap<String, Loopback> active = new ConcurrentHashMap<>();
    private AndroidAudio() {}
    public static boolean hasPermission(Context context) {
        return context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED;
    }
    public static String devices(Context context) {
        JSONArray result = new JSONArray();
        if (!hasPermission(context)) return result.toString();
        for (AudioDeviceInfo device : context.getSystemService(AudioManager.class).getDevices(AudioManager.GET_DEVICES_INPUTS)) {
            if (device.getType() == AudioDeviceInfo.TYPE_TELEPHONY || device.getType() == AudioDeviceInfo.TYPE_REMOTE_SUBMIX) continue;
            try {
                JSONObject item = new JSONObject();
                item.put("deviceId", Integer.toString(device.getId()));
                item.put("label", device.getProductName().toString() + " (" + device.getId() + ")");
                result.put(item);
            } catch (JSONException impossible) { throw new IllegalStateException(impossible); }
        }
        return result.toString();
    }
    public static synchronized boolean activate(Context context, String id, float gain, int latency, boolean echo) {
        if (!hasPermission(context)) return false;
        deactivate(id);
        AudioDeviceInfo input = null;
        for (AudioDeviceInfo d : context.getSystemService(AudioManager.class).getDevices(AudioManager.GET_DEVICES_INPUTS))
            if (Integer.toString(d.getId()).equals(id)) input = d;
        if (input == null) return false;
        try {
            Loopback loop = new Loopback(input, gain, latency, echo);
            active.put(id, loop); loop.start(); return true;
        } catch (RuntimeException e) { Log.e("PiKaraokeAudio", "Microphone could not start", e); return false; }
    }
    public static void deactivate(String id) { Loopback loop = active.remove(id); if (loop != null) loop.close(); }
    public static void volume(String id, float gain) { Loopback loop = active.get(id); if (loop != null) loop.gain = Math.max(0, Math.min(1, gain)); }
    public static void stopAll() { for (String id : active.keySet()) deactivate(id); }

    private static final class Loopback extends Thread {
        private final AudioRecord record;
        private final AudioTrack track;
        private final AcousticEchoCanceler echo;
        private volatile boolean running = true;
        volatile float gain;
        Loopback(AudioDeviceInfo device, float volume, int latency, boolean cancelEcho) {
            super("PiKaraoke microphone");
            gain = Math.max(0, Math.min(1, volume));
            int bytes = Math.max(48000 * Math.max(10, Math.min(200, latency)) / 1000 * 2,
                AudioRecord.getMinBufferSize(48000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT));
            bytes = Math.max(bytes, AudioTrack.getMinBufferSize(48000, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT));
            record = new AudioRecord.Builder().setAudioSource(MediaRecorder.AudioSource.VOICE_RECOGNITION)
                .setAudioFormat(new AudioFormat.Builder().setSampleRate(48000).setChannelMask(AudioFormat.CHANNEL_IN_MONO).setEncoding(AudioFormat.ENCODING_PCM_16BIT).build())
                .setBufferSizeInBytes(bytes * 2).build();
            record.setPreferredDevice(device);
            track = new AudioTrack.Builder().setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build())
                .setAudioFormat(new AudioFormat.Builder().setSampleRate(48000).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).setEncoding(AudioFormat.ENCODING_PCM_16BIT).build())
                .setBufferSizeInBytes(bytes * 2).setTransferMode(AudioTrack.MODE_STREAM).setPerformanceMode(AudioTrack.PERFORMANCE_MODE_LOW_LATENCY).build();
            echo = cancelEcho && AcousticEchoCanceler.isAvailable() ? AcousticEchoCanceler.create(record.getAudioSessionId()) : null;
            if (echo != null) echo.setEnabled(true);
            record.startRecording(); track.play();
        }
        @Override public void run() {
            Process.setThreadPriority(Process.THREAD_PRIORITY_AUDIO);
            short[] data = new short[480];
            try {
                while(running) {
                    int count = record.read(data, 0, data.length, AudioRecord.READ_BLOCKING);
                    if(count <= 0) break;
                    float current = gain;
                    for(int i=0;i<count;i++) data[i] = (short)(data[i] * current);
                    int offset=0;
                    while(running && offset<count) { int n=track.write(data,offset,count-offset,AudioTrack.WRITE_BLOCKING); if(n<=0) break; offset+=n; }
                }
            } finally {
                record.release(); track.release(); if(echo!=null) echo.release();
            }
        }
        void close() {
            running=false;
            try { record.stop(); } catch(IllegalStateException ignored) { }
            try { join(1000); } catch(InterruptedException e) { Thread.currentThread().interrupt(); }
        }
    }
}
