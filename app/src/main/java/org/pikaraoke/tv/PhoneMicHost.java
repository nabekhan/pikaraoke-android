package org.pikaraoke.tv;

import android.content.Context;
import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioTrack;
import android.os.Process;
import android.util.Log;
import java.util.*;
import java.util.concurrent.*;
import org.json.*;
import livekit.org.webrtc.*;

/** Four independent data-only WebRTC peers mixed into one media output. */
public final class PhoneMicHost {
    public static final int MAX_MICS = 4;
    private static PhoneMicHost instance;
    private static boolean initialized;
    private final ConcurrentHashMap<String, Peer> peers = new ConcurrentHashMap<>();
    private final PeerConnectionFactory factory;
    private final ScheduledExecutorService cleanup = Executors.newSingleThreadScheduledExecutor();
    private final Object disposalLock = new Object();
    private volatile boolean running = true;
    private final Thread mixer;
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
    public synchronized String join(String name) throws JSONException {
        if (!running) throw new IllegalStateException("The room has stopped.");
        if (peers.size() >= MAX_MICS) throw new IllegalStateException("All four microphones are in use. Try again when someone disconnects.");
        boolean[] used = new boolean[MAX_MICS + 1];
        for (Peer p : peers.values()) used[p.slot] = true;
        int slot = 1; while (used[slot]) slot++;
        Peer peer = new Peer(UUID.randomUUID().toString(), slot, name);
        peers.put(peer.id, peer);
        return new JSONObject().put("id", peer.id).put("slot", slot).put("max", MAX_MICS).toString();
    }
    public String status() throws JSONException {
        JSONArray active = new JSONArray();
        for (Peer p : peers.values()) synchronized (p) {
            active.put(new JSONObject().put("slot", p.slot).put("name", p.name)
                .put("muted", p.pcm.muted).put("connected", p.connected)
                .put("received_packets", p.pcm.received).put("buffer_frames", p.pcm.queuedFrames()));
        }
        return new JSONObject().put("max", MAX_MICS).put("active", active)
            .put("written_frames", writtenFrames).put("mixed_frames", mixedFrames).put("output_error", outputError).toString();
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
        public synchronized void onDataChannel(DataChannel data) {
            if (!data.label().equals("audio") || channel != null || !peers.containsKey(id)) { data.close(); return; }
            channel = data;
            connected = data.state() == DataChannel.State.OPEN;
            data.registerObserver(new DataChannel.Observer() {
                public void onBufferedAmountChange(long previous) { }
                public void onStateChange() { synchronized (Peer.this) {
                    if (channel != data) return;
                    connected = data.state() == DataChannel.State.OPEN;
                    if (connected) heartbeat = System.nanoTime();
                    if (data.state() == DataChannel.State.CLOSED) leave(id);
                } }
                public void onMessage(DataChannel.Buffer message) {
                    if (message.binary && message.data.remaining() <= 2064) pcm.push(message.data, System.nanoTime());
                }
            });
        }
        public void onIceGatheringChange(PeerConnection.IceGatheringState state) {
            if (state == PeerConnection.IceGatheringState.COMPLETE) ice.complete(null);
        }
        public void onIceConnectionChange(PeerConnection.IceConnectionState state) {
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
        AudioTrack track = null;
        try {
            int minimum = AudioTrack.getMinBufferSize(48000, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT);
            track = new AudioTrack.Builder().setAudioAttributes(new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build())
                .setAudioFormat(new AudioFormat.Builder().setSampleRate(48000).setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT).build())
                .setTransferMode(AudioTrack.MODE_STREAM).setBufferSizeInBytes(Math.max(minimum, 1920))
                .setPerformanceMode(AudioTrack.PERFORMANCE_MODE_LOW_LATENCY).build();
            if (track.getState() != AudioTrack.STATE_INITIALIZED) throw new IllegalStateException("Audio output unavailable");
            track.play();
            float[] mix = new float[240];
            short[] pcm = new short[240];
            while (running) {
                Arrays.fill(mix, 0);
                long now = System.nanoTime();
                for (Peer p : peers.values()) p.pcm.mix(mix, now);
                float peak = 1;
                for (float value : mix) peak = Math.max(peak, Math.abs(value));
                for (int i = 0; i < pcm.length; i++) pcm[i] = (short)(mix[i] / peak * 32767);
                int offset = 0;
                while (running && offset < pcm.length) {
                    int n = track.write(pcm, offset, pcm.length - offset, AudioTrack.WRITE_BLOCKING);
                    if (n <= 0) throw new IllegalStateException("Audio output stopped: " + n);
                    for (int i = offset; i < offset + n; i++) if (pcm[i] != 0) mixedFrames++;
                    offset += n; writtenFrames += n;
                }
            }
        } catch (RuntimeException e) { outputError = "TV audio output stopped. Restart the room."; Log.e("PiKaraokePhoneMic", outputError, e); }
        finally { if (track != null) track.release(); }
    }
    private void close() {
        synchronized (this) { running = false; }
        for (String id : peers.keySet()) leave(id);
        synchronized (disposalLock) { cleanup.shutdown(); }
        try { mixer.join(1500); cleanup.awaitTermination(3, TimeUnit.SECONDS); }
        catch (InterruptedException e) { Thread.currentThread().interrupt(); }
        factory.dispose();
    }
}
