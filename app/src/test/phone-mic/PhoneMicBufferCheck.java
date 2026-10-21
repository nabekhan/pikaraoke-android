import java.nio.*;
import org.pikaraoke.tv.PhoneMicBuffer;
import org.pikaraoke.tv.PhoneMicOutput;

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
        check(b.queuedFrames() <= 1920, "backlog bounded to 40ms");
        out=new float[480]; b.mix(out,now+300_000_000L);
        for(float value:out) check(value==0,"stale audio silenced");
        float[] levels = new float[3];
        for (int gain=0; gain<=2; gain++) {
            PhoneMicBuffer boosted = new PhoneMicBuffer();
            boosted.controls(gain,false,0);
            for(int seq=0;seq<4;seq++) boosted.push(packet(seq,3,(short)500),now);
            float[] output = new float[480]; boosted.mix(output,now);
            levels[gain]=output[100];
        }
        check(levels[0]==0,"zero gain is silent");
        check(Math.abs(levels[1]-4000f/32768)<.00001,"default phone level includes 18 dB of input gain");
        check(Math.abs(levels[2]-8000f/32768)<.00001,"maximum phone level is 16 times the captured signal");
        check(Math.abs(levels[2]-2*levels[1])<.00001,"boost doubles actual decoded PCM amplitude");
        short[] phoneLevels = new short[3];
        PhoneMicOutput.encode(levels,phoneLevels);
        check(Math.abs(phoneLevels[1]-4000)<=1,"default phone boost reaches final PCM output");
        check(Math.abs(phoneLevels[2]-8000)<=1,"maximum phone boost reaches final PCM output");
        short[] ordinary = new short[4], boosted = new short[4];
        PhoneMicOutput.encode(new float[]{.6f,.1f,-.1f,-.6f},ordinary);
        PhoneMicOutput.encode(new float[]{1.2f,.2f,-.2f,-1.2f},boosted);
        check(boosted[0]>ordinary[0],"final output boost stays louder even when peaks need limiting");
        check(Math.abs(boosted[1]-ordinary[1]*2)<=1,"peak limiting must not cancel other samples' gain");
        check(boosted[3]<ordinary[3] && boosted[0]>0,"output remains bounded with correct polarity");
        PhoneMicBuffer loudPhone = new PhoneMicBuffer();
        loudPhone.controls(2,false,0);
        for(int seq=0;seq<4;seq++) loudPhone.push(packet(seq,3,(short)30000),now);
        float[] loudMix = new float[480]; loudPhone.mix(loudMix,now);
        short[] loudOutput = new short[480]; PhoneMicOutput.encode(loudMix,loudOutput);
        check(loudOutput[100]>30000 && loudOutput[100]<=32767,"boosted loud input is limited without wrapping polarity");
        loudPhone.discardAudio();
        float[] resumed = new float[480]; loudPhone.mix(resumed,now);
        for(float value:resumed) check(value==0,"output recovery discards old queued audio and reverb");
        check(loudPhone.gain==2 && !loudPhone.muted,"output recovery keeps microphone controls");
        PhoneMicBuffer[] four = new PhoneMicBuffer[4];
        for(int j=0;j<4;j++) {
            four[j]=new PhoneMicBuffer();
            for(int seq=0;seq<4;seq++) four[j].push(packet(seq,2,(short)2000),now);
        }
        out=new float[480]; for(PhoneMicBuffer input:four) input.mix(out,now);
        check(out[100]>.12,"four 44.1kHz sources mixed at 48kHz");
        check(Float.isFinite(out[100]),"finite output");
        System.out.println("PCM: framing, sequence wrap/reorder, mute, stale audio, bounded backlog, four-source mixing passed");
    }
}
