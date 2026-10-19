import java.nio.*;
import org.pikaraoke.tv.PhoneMicBuffer;

/** Exercises the actual receiver independently of Android/WebRTC. */
public class PhoneMicBufferCheck {
    static ByteBuffer packet(int sequence, int rate, short sample) {
        ByteBuffer b = ByteBuffer.allocate(528).order(ByteOrder.LITTLE_ENDIAN);
        b.putLong(0).putShort((short)sequence).putShort((short)256);
        b.put((byte)rate).put((byte)16).put((byte)1).put((byte)1);
        for (int i=0;i<256;i++) b.putShort(sample);
        b.flip(); return b;
    }
    static void check(boolean value, String message) { if (!value) throw new AssertionError(message); }
    public static void main(String[] args) {
        long now = 1_000_000_000L;
        PhoneMicBuffer b = new PhoneMicBuffer();
        check(!b.push(ByteBuffer.allocate(10), now), "short packets rejected");
        ByteBuffer stereo = packet(0,3,(short)1000); stereo.put(15,(byte)2);
        check(!b.push(stereo,now), "stereo rejected");
        for (int seq : new int[]{65534,0,65535,1,2}) check(b.push(packet(seq,3,(short)12000), now), "wrap/reorder accepted");
        check(!b.push(packet(1,3,(short)12000),now), "duplicate rejected");
        float[] out = new float[480]; b.mix(out,now);
        check(out[100] > .2, "real PCM decoded and rendered");
        check(!b.push(packet(65534,3,(short)12000),now), "already played packet rejected");
        b.controls(1,true,3); out=new float[480]; b.mix(out,now);
        for(float value:out) check(value==0,"mute also clears reverb");
        b.controls(1,false,0);
        for(int seq=3;seq<100;seq++) b.push(packet(seq,3,(short)2000),now);
        check(b.queuedFrames() <= 3840, "backlog bounded to 80ms");
        out=new float[480]; b.mix(out,now+300_000_000L);
        for(float value:out) check(value==0,"stale audio silenced");
        PhoneMicBuffer[] four = new PhoneMicBuffer[4];
        for(int j=0;j<4;j++) {
            four[j]=new PhoneMicBuffer();
            for(int seq=0;seq<8;seq++) four[j].push(packet(seq,2,(short)2000),now);
        }
        out=new float[480]; for(PhoneMicBuffer input:four) input.mix(out,now);
        check(out[100]>.12,"four 44.1kHz sources mixed at 48kHz");
        check(Float.isFinite(out[100]),"finite output");
        System.out.println("PCM: framing, sequence wrap/reorder, mute, stale audio, bounded backlog, four-source mixing passed");
    }
}
