package org.pikaraoke.tv;

import android.content.Context;
import android.media.AudioTrack;
import android.media.AudioManager;
import android.os.Process;
import android.os.PowerManager;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import java.util.*;
import java.util.concurrent.*;
import org.json.*;
import livekit.org.webrtc.*;

/** Four independent data-only WebRTC peers mixed into one media output. */
public final class PhoneMicHost {
    public static final int MAX_MICS = 4;
    private volatile int maxMics = 2;
    private static PhoneMicHost instance;
    private static boolean initialized;
    private final ConcurrentHashMap<String, Peer> peers = new ConcurrentHashMap<>();
    private final PeerConnectionFactory factory;
    private final ScheduledExecutorService cleanup = Executors.newSingleThreadScheduledExecutor();
    private final Object disposalLock = new Object();
    private volatile boolean running = true;
    private final Thread mixer;
    private final int outputBurstFrames;
    private final PowerManager power;
    private final AudioManager audio;
    private volatile int routeGeneration;
    private final android.media.AudioDeviceCallback devices = new android.media.AudioDeviceCallback() {
        private void changed(android.media.AudioDeviceInfo[] changed) {
            for (android.media.AudioDeviceInfo device : changed) if (device.isSink()) { routeGeneration++; return; }
        }
        @Override public void onAudioDevicesAdded(android.media.AudioDeviceInfo[] added) { changed(added); }
        @Override public void onAudioDevicesRemoved(android.media.AudioDeviceInfo[] removed) { changed(removed); }
    };
    private volatile PhoneMicPlayback outputTrack;
    private volatile String outputBackend = "";
    private volatile double outputLatencyMillis = -1;
    private volatile int outputBufferFrames, outputUnderruns;
    private volatile int outputRestarts;
    private volatile long outputPlaybackFrames;
    private volatile long writtenFrames;
    private volatile long mixedFrames;
    private volatile String outputError = "";

    public static synchronized PhoneMicHost get(Context context) {
        if (instance == null) instance = new PhoneMicHost(context.getApplicationContext());
        return instance;
    }
    public static synchronized void stopAll() {
        if (instance != null) { instance.close(); instance = null; }
    }
    private PhoneMicHost(Context context) {
        power = (PowerManager) context.getSystemService(Context.POWER_SERVICE);
        audio = (AudioManager) context.getSystemService(Context.AUDIO_SERVICE);
        audio.registerAudioDeviceCallback(devices, new Handler(Looper.getMainLooper()));
        int burst = 240;
        try {
            int reported = Integer.parseInt(audio.getProperty(AudioManager.PROPERTY_OUTPUT_FRAMES_PER_BUFFER));
            if (reported >= 48 && reported <= 4096) burst = reported;
        } catch (RuntimeException ignored) { /* Some TVs do not report their output burst. */ }
        outputBurstFrames = burst;
        if (!initialized) {
            PeerConnectionFactory.initialize(PeerConnectionFactory.InitializationOptions.builder(context).createInitializationOptions());
            initialized = true;
        }
        factory = PeerConnectionFactory.builder().createPeerConnectionFactory();
        mixer = new Thread(this::mix, "PiKaraoke phone mix");
        mixer.start();
        cleanup.scheduleAtFixedRate(() -> {
            long now = System.nanoTime();
            for (Peer p : peers.values()) if (now - p.heartbeat > (p.connected ? 30_000_000_000L : 15_000_000_000L)) leave(p.id);
        }, 5, 5, TimeUnit.SECONDS);
    }
    public synchronized void setMaxMics(int limit) {
        if (limit < 1 || limit > MAX_MICS) throw new IllegalArgumentException("Choose 1 to 4 phone mics.");
        maxMics = limit;
    }
    public synchronized String join(String name) throws JSONException {
        if (!running) throw new IllegalStateException("The room has stopped.");
        if (peers.size() >= maxMics) throw new IllegalStateException("All microphones are in use. Try again when someone disconnects.");
        boolean[] used = new boolean[MAX_MICS + 1];
        for (Peer p : peers.values()) used[p.slot] = true;
        int slot = 1; while (used[slot]) slot++;
        Peer peer = new Peer(UUID.randomUUID().toString(), slot, name);
        peers.put(peer.id, peer);
        return new JSONObject().put("id", peer.id).put("slot", slot).put("max", maxMics).toString();
    }
    public String status() throws JSONException {
        JSONArray active = new JSONArray();
        for (Peer p : peers.values()) synchronized (p) {
            active.put(new JSONObject().put("slot", p.slot).put("name", p.name)
                .put("muted", p.pcm.muted).put("connected", p.connected)
                .put("ice_state", p.iceState.toString())
                .put("received_packets", p.pcm.received).put("buffer_frames", p.pcm.queuedFrames()).put("underruns", p.pcm.underruns));
        }
        return new JSONObject().put("max", maxMics).put("active", active)
            .put("written_frames", writtenFrames).put("mixed_frames", mixedFrames).put("output_error", outputError).put("output_buffer_frames", outputBufferFrames)
            .put("output_underruns", outputUnderruns).put("output_restarts", outputRestarts)
            .put("output_playback_frames", outputPlaybackFrames).put("output_backend", outputBackend)
            .put("output_latency_ms", outputLatencyMillis).toString();
    }
    private Peer peer(String id) {
        Peer p = peers.get(id);
        if (p == null) throw new IllegalArgumentException("Microphone disconnected. Tap the mic to reconnect.");
        p.heartbeat = System.nanoTime(); return p;
    }
    public void heartbeat(String id) { peer(id); }
    public void controls(String id, float gain, boolean muted, int reverb) { peer(id).pcm.controls(gain, muted, reverb); }
    public void leave(String id) {
        synchronized (disposalLock) {
            Peer p = peers.remove(id);
            if (p != null) {
                p.pcm.controls(0, true, 0);
                // Native callbacks must not synchronously dispose their own peer.
                cleanup.execute(p::dispose);
            }
        }
    }
    public String answer(String id, String offer) throws Exception {
        Peer p = peer(id);
        synchronized (this) { synchronized (p) {
            if (!running || peers.get(id) != p) throw new IllegalArgumentException("Microphone disconnected.");
            if (p.connection != null) throw new IllegalArgumentException("Microphone is already connected.");
            PeerConnection.RTCConfiguration cfg = new PeerConnection.RTCConfiguration(Collections.emptyList());
            cfg.sdpSemantics = PeerConnection.SdpSemantics.UNIFIED_PLAN;
            p.connection = factory.createPeerConnection(cfg, p);
            if (p.connection == null) throw new IllegalStateException("Could not start the microphone connection.");
        } }
        try {
            CompletableFuture<Void> remote = new CompletableFuture<>();
            synchronized (p) { p.requireConnection().setRemoteDescription(new Description(remote), new SessionDescription(SessionDescription.Type.OFFER, offer)); }
            remote.get(8, TimeUnit.SECONDS);
            CompletableFuture<SessionDescription> created = new CompletableFuture<>();
            synchronized (p) { p.requireConnection().createAnswer(new SdpObserver() {
                public void onCreateSuccess(SessionDescription d) { created.complete(d); }
                public void onCreateFailure(String e) { created.completeExceptionally(new IllegalStateException(e)); }
                public void onSetSuccess() { }
                public void onSetFailure(String e) { }
            }, new MediaConstraints()); }
            SessionDescription answer = created.get(8, TimeUnit.SECONDS);
            CompletableFuture<Void> local = new CompletableFuture<>();
            synchronized (p) { p.requireConnection().setLocalDescription(new Description(local), answer); }
            local.get(8, TimeUnit.SECONDS);
            p.ice.get(10, TimeUnit.SECONDS);
            synchronized (p) { return new JSONObject().put("type", "answer").put("sdp", p.requireConnection().getLocalDescription().description).toString(); }
        } catch (Exception e) { leave(id); throw e; }
    }
    private static final class Description implements SdpObserver {
        private final CompletableFuture<Void> result;
        Description(CompletableFuture<Void> f) { result = f; }
        public void onCreateSuccess(SessionDescription d) { }
        public void onCreateFailure(String e) { result.completeExceptionally(new IllegalStateException(e)); }
        public void onSetSuccess() { result.complete(null); }
        public void onSetFailure(String e) { result.completeExceptionally(new IllegalStateException(e)); }
    }
    private final class Peer implements PeerConnection.Observer {
        final String id, name;
        final int slot;
        final PhoneMicBuffer pcm = new PhoneMicBuffer();
        final CompletableFuture<Void> ice = new CompletableFuture<>();
        volatile long heartbeat = System.nanoTime();
        volatile PeerConnection connection;
        volatile DataChannel channel;
        volatile boolean connected;
        volatile PeerConnection.IceConnectionState iceState = PeerConnection.IceConnectionState.NEW;
        Peer(String id, int slot, String name) { this.id = id; this.slot = slot; this.name = name; }
        PeerConnection requireConnection() {
            if (connection == null || !peers.containsKey(id)) throw new IllegalArgumentException("Microphone disconnected");
            return connection;
        }
        void dispose() {
            DataChannel oldChannel;
            PeerConnection oldConnection;
            synchronized (this) {
                oldChannel = channel; channel = null; connected = false;
                oldConnection = connection; connection = null;
            }
            // close()/dispose() may wait for callbacks; never hold the peer monitor.
            if (oldChannel != null) { oldChannel.unregisterObserver(); oldChannel.close(); oldChannel.dispose(); }
            if (oldConnection != null) { oldConnection.close(); oldConnection.dispose(); }
        }
        public void onDataChannel(DataChannel data) {
            // WebRTC invokes observers on its signaling thread. Never wait on a
            // monitor held across a synchronous JNI call back to that thread.
            enqueue(() -> {
                if (!data.label().equals("audio") || channel != null || !peers.containsKey(id)) {
                    data.close(); data.dispose(); return;
                }
                channel = data;
                data.registerObserver(new DataChannel.Observer() {
                    public void onBufferedAmountChange(long previous) { }
                    public void onStateChange() { enqueue(() -> updateState(data)); }
                    public void onMessage(DataChannel.Buffer message) {
                        if (message.binary && message.data.remaining() <= 2064) pcm.push(message.data, System.nanoTime());
                    }
                });
                updateState(data);
            });
        }
        private void updateState(DataChannel data) {
            if (channel != data) return;
            connected = data.state() == DataChannel.State.OPEN;
            if (connected) heartbeat = System.nanoTime();
            if (data.state() == DataChannel.State.CLOSED) leave(id);
        }
        private void enqueue(Runnable action) {
            try { cleanup.execute(action); }
            catch (RejectedExecutionException ignored) {
                // A final native callback can race room shutdown. Dispose its
                // retained channel off the native callback thread too.
                new Thread(action, "PiKaraoke mic disposal").start();
            }
        }
        public void onIceGatheringChange(PeerConnection.IceGatheringState state) {
            if (state == PeerConnection.IceGatheringState.COMPLETE) ice.complete(null);
        }
        public void onIceConnectionChange(PeerConnection.IceConnectionState state) {
            iceState = state;
            Log.i("PiKaraokePhoneMic", "Slot " + slot + " ICE " + state);
            if (state == PeerConnection.IceConnectionState.FAILED || state == PeerConnection.IceConnectionState.CLOSED) leave(id);
            if (state == PeerConnection.IceConnectionState.DISCONNECTED) {
                try {
                    cleanup.schedule(() -> { synchronized (Peer.this) { if (connection != null && connection.iceConnectionState() == PeerConnection.IceConnectionState.DISCONNECTED) leave(id); } }, 5, TimeUnit.SECONDS);
                } catch (RejectedExecutionException ignored) { /* Room shutdown already owns disposal. */ }
            }
        }
        public void onSignalingChange(PeerConnection.SignalingState state) { }
        public void onIceConnectionReceivingChange(boolean receiving) { }
        public void onIceCandidate(IceCandidate candidate) { }
        public void onIceCandidatesRemoved(IceCandidate[] candidates) { }
        public void onAddStream(MediaStream stream) { }
        public void onRemoveStream(MediaStream stream) { }
        public void onRenegotiationNeeded() { }
    }
    private void mix() {
        Process.setThreadPriority(Process.THREAD_PRIORITY_AUDIO);
        PhoneMicPlayback track = null;
        boolean opened = false;
        try {
            float[] mix = new float[240];
            short[] pcm = new short[240];
            long lastWrite = System.nanoTime();
            long trackWrittenFrames = 0;
            int openedRoute = routeGeneration;
            output: while (running) {
                if (track != null && routeGeneration != openedRoute) {
                    track.close(); track = null; outputTrack = null;
                }
                // Android pauses media tracks in standby and need not resume them
                // after HDMI reconnects. Leave the system asleep; reopen on wake.
                if (!power.isInteractive()) {
                    if (track != null) {
                        track.close(); track = null; outputTrack = null;
                        outputPlaybackFrames = 0;
                    }
                    java.util.concurrent.locks.LockSupport.parkNanos(100_000_000L);
                    continue;
                }
                if (track == null) {
                    openedRoute = routeGeneration;
                    for (Peer p : peers.values()) p.pcm.discardAudio();
                    track = PhoneMicPlayback.open(outputBurstFrames); outputTrack = track;
                    outputBackend = track.backend(); outputBufferFrames = track.bufferFrames();
                    if (opened) outputRestarts++;
                    opened = true;
                    outputPlaybackFrames = 0; outputUnderruns = 0;
                    trackWrittenFrames = 0;
                    lastWrite = System.nanoTime();
                }
                Arrays.fill(mix, 0);
                long now = System.nanoTime();
                for (Peer p : peers.values()) p.pcm.mix(mix, now);
                PhoneMicOutput.encode(mix, pcm);
                int offset = 0;
                while (running && offset < pcm.length) {
                    if (routeGeneration != openedRoute) continue output;
                    // A blocking write can wait forever on a paused/invalidated
                    // HDMI track. Poll with a deadline so shutdown and recovery run.
                    int n = track.write(pcm, offset, pcm.length - offset);
                    outputPlaybackFrames = track.playbackFrames();
                    outputLatencyMillis = track.latencyMillis();
                    if (n == AudioTrack.ERROR_DEAD_OBJECT || (n == 0 && System.nanoTime() - lastWrite > 500_000_000L)) {
                        Log.w("PiKaraokePhoneMic", "Reopening stalled audio output");
                        track.close(); track = null; outputTrack = null;
                        if (n < 0) java.util.concurrent.locks.LockSupport.parkNanos(50_000_000L);
                        // Drop this old block rather than replaying it on wake.
                        continue output;
                    }
                    if (n < 0) throw new IllegalStateException("Audio output stopped: " + n);
                    if (n == 0) {
                        if (!power.isInteractive()) continue output;
                        java.util.concurrent.locks.LockSupport.parkNanos(1_000_000L);
                        continue;
                    }
                    lastWrite = System.nanoTime();
                    for (int i = offset; i < offset + n; i++) if (pcm[i] != 0) mixedFrames++;
                    offset += n; writtenFrames += n; trackWrittenFrames += n;
                    int underruns = track.underruns();
                    if (underruns > outputUnderruns && trackWrittenFrames > 48000) {
                        track.setBufferFrames(Math.min(track.capacityFrames(), outputBufferFrames + track.burstFrames(outputBurstFrames)));
                        outputBufferFrames = track.bufferFrames();
                    }
                    outputUnderruns = underruns;
                }
            }
        } catch (RuntimeException e) { outputError = "TV audio output stopped. Restart the room."; Log.e("PiKaraokePhoneMic", outputError, e); }
        finally { if (track != null) track.close(); outputTrack = null; }
    }
    private void close() {
        synchronized (this) { running = false; }
        audio.unregisterAudioDeviceCallback(devices);
        for (String id : peers.keySet()) leave(id);
        synchronized (disposalLock) { cleanup.shutdown(); }
        try { mixer.join(1500); cleanup.awaitTermination(3, TimeUnit.SECONDS); }
        catch (InterruptedException e) { Thread.currentThread().interrupt(); }
        factory.dispose();
    }
}
