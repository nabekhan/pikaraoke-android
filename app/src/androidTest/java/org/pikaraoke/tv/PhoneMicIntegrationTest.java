package org.pikaraoke.tv;

import android.content.*;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.*;
import java.nio.*;
import java.nio.file.Files;
import java.security.cert.*;
import java.util.*;
import java.util.concurrent.*;
import org.json.*;
import org.junit.Test;
import org.junit.runner.RunWith;
import livekit.org.webrtc.*;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class PhoneMicIntegrationTest {
    private static final int TIMEOUT = 15;
    static class Observer implements PeerConnection.Observer {
        final CompletableFuture<Void> ice = new CompletableFuture<>();
        volatile PeerConnection.IceConnectionState iceState=PeerConnection.IceConnectionState.NEW;
        public void onIceGatheringChange(PeerConnection.IceGatheringState s) { if(s==PeerConnection.IceGatheringState.COMPLETE) ice.complete(null); }
        public void onSignalingChange(PeerConnection.SignalingState s) { }
        public void onIceConnectionChange(PeerConnection.IceConnectionState s) { iceState=s; }
        public void onIceConnectionReceivingChange(boolean r) { }
        public void onIceCandidate(IceCandidate c) { }
        public void onIceCandidatesRemoved(IceCandidate[] c) { }
        public void onAddStream(MediaStream s) { }
        public void onRemoveStream(MediaStream s) { }
        public void onDataChannel(DataChannel d) { }
        public void onRenegotiationNeeded() { }
    }
    static class Description implements SdpObserver {
        final CompletableFuture<SessionDescription> created = new CompletableFuture<>();
        final CompletableFuture<Void> set = new CompletableFuture<>();
        public void onCreateSuccess(SessionDescription d) { created.complete(d); }
        public void onSetSuccess() { set.complete(null); }
        public void onCreateFailure(String e) { created.completeExceptionally(new IllegalStateException(e)); }
        public void onSetFailure(String e) { set.completeExceptionally(new IllegalStateException(e)); }
    }
    @Test public void fourDataChannelsProduceNativeAudioAndReleaseSlots() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        PhoneMicHost.stopAll();
        PhoneMicHost host = PhoneMicHost.get(context);
        PeerConnectionFactory clients = PeerConnectionFactory.builder().createPeerConnectionFactory();
        List<PeerConnection> connections = new ArrayList<>();
        List<DataChannel> channels = new ArrayList<>();
        List<String> tokens = new ArrayList<>();
        try {
            for(int i=0;i<4;i++) {
                String id = new JSONObject(host.join("Phone "+(i+1))).getString("id"); tokens.add(id);
                Observer observer = new Observer();
                PeerConnection peer = clients.createPeerConnection(new PeerConnection.RTCConfiguration(Collections.emptyList()), observer);
                assertNotNull(peer); connections.add(peer);
                DataChannel.Init init = new DataChannel.Init(); init.ordered=false; init.maxRetransmits=0;
                DataChannel channel = peer.createDataChannel("audio",init); channels.add(channel);
                Description offer = new Description(); peer.createOffer(offer,new MediaConstraints());
                SessionDescription local = offer.created.get(TIMEOUT,TimeUnit.SECONDS);
                Description setLocal = new Description(); peer.setLocalDescription(setLocal,local); setLocal.set.get(TIMEOUT,TimeUnit.SECONDS);
                observer.ice.get(TIMEOUT,TimeUnit.SECONDS);
                JSONObject answer = new JSONObject(host.answer(id,peer.getLocalDescription().description));
                Description setRemote = new Description();
                peer.setRemoteDescription(setRemote,new SessionDescription(SessionDescription.Type.ANSWER,answer.getString("sdp")));
                setRemote.set.get(TIMEOUT,TimeUnit.SECONDS);
                long deadline=System.currentTimeMillis()+15000;
                while(channel.state()!=DataChannel.State.OPEN && System.currentTimeMillis()<deadline) Thread.sleep(20);
                assertEquals("sender ICE="+observer.iceState+"; receiver="+host.status(),DataChannel.State.OPEN,channel.state());
            }
            try { host.join("Fifth phone"); fail("A fifth microphone was admitted"); }
            catch(IllegalStateException expected) { }
            for(int seq=0;seq<160;seq++) {
                ByteBuffer packet=ByteBuffer.allocateDirect(528).order(ByteOrder.LITTLE_ENDIAN);
                packet.putLong(0).putShort((short)seq).putShort((short)256).put((byte)3).put((byte)16).put((byte)1).put((byte)1);
                for(int j=0;j<256;j++) packet.putShort((short)(Math.sin((seq*256+j)*.03)*4000));
                packet.flip();
                for(DataChannel channel:channels) assertTrue(channel.send(new DataChannel.Buffer(packet.duplicate(),true)));
                Thread.sleep(6);
            }
            JSONObject status = new JSONObject(host.status());
            assertEquals("",status.getString("output_error"));
            assertTrue("Decoded samples did not reach AudioTrack",status.getLong("mixed_frames")>1000);
            JSONArray active=status.getJSONArray("active"); assertEquals(4,active.length());
            for(int i=0;i<4;i++) assertTrue("Missing input",active.getJSONObject(i).getLong("received_packets")>30);
            host.controls(tokens.get(0),.3f,true,2);
            host.leave(tokens.get(0));
            assertEquals(3,new JSONObject(host.status()).getJSONArray("active").length());
            JSONObject replacement=new JSONObject(host.join("Replacement"));
            assertEquals(1,replacement.getInt("slot"));
            host.leave(replacement.getString("id"));
        } finally {
            PhoneMicHost.stopAll();
            for(DataChannel c:channels) { c.close(); c.dispose(); }
            for(PeerConnection p:connections) { p.close(); p.dispose(); }
            clients.dispose();
        }
    }
    @Test public void certificatesAreUniqueAndAddressChangesKeepTheSameCa() throws Exception {
        Context base=InstrumentationRegistry.getInstrumentation().getTargetContext();
        File root=new File(base.getCacheDir(),"certificate-check-"+UUID.randomUUID());
        Context one=new ContextWrapper(base) { @Override public File getNoBackupFilesDir() { return new File(root,"one"); } };
        Context two=new ContextWrapper(base) { @Override public File getNoBackupFilesDir() { return new File(root,"two"); } };
        try {
            JSONObject first=new JSONObject(PhoneMicCertificates.ensure(one,"192.0.2.1"));
            JSONObject other=new JSONObject(PhoneMicCertificates.ensure(two,"192.0.2.1"));
            assertNotEquals(first.getString("fingerprint"),other.getString("fingerprint"));
            JSONObject changed=new JSONObject(PhoneMicCertificates.ensure(one,"192.0.2.2"));
            assertEquals(first.getString("fingerprint"),changed.getString("fingerprint"));
            CertificateFactory cf=CertificateFactory.getInstance("X.509");
            X509Certificate ca,server;
            try(InputStream in=new FileInputStream(changed.getString("ca"))) { ca=(X509Certificate)cf.generateCertificate(in); }
            try(InputStream in=new FileInputStream(changed.getString("cert"))) { server=(X509Certificate)cf.generateCertificate(in); }
            server.verify(ca.getPublicKey()); server.checkValidity();
            assertTrue(ca.getBasicConstraints()>=0); assertEquals(-1,server.getBasicConstraints());
            assertTrue(server.getSubjectAlternativeNames().toString().contains("192.0.2.2"));
        } finally {
            try(java.util.stream.Stream<java.nio.file.Path> files=Files.walk(root.toPath())) {
                files.sorted(Comparator.reverseOrder()).forEach(path -> { try { Files.delete(path); } catch(IOException ignored) { } });
            }
        }
    }
}
