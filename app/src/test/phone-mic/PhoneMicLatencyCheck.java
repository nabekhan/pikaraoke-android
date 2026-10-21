/** Synthetic PCM impulse benchmark using the actual receiver; no hardware or transport delay. */
import java.nio.*;
import java.util.*;
import org.pikaraoke.tv.PhoneMicBuffer;
public final class PhoneMicLatencyCheck {
    record Delivery(long at, int seq, ByteBuffer bytes) {}
    static ByteBuffer packet(int seq, int samples) {
        ByteBuffer b=ByteBuffer.allocate(16+samples*2).order(ByteOrder.LITTLE_ENDIAN);
        b.putLong(0).putShort((short)seq).putShort((short)samples).put((byte)3).put((byte)16).put((byte)1).put((byte)1);
        for(int i=0;i<samples;i++) {
            int position=seq*samples+i;
            boolean impulse=position>=4800 && position%4800<48;
            b.putShort(impulse?(short)12000:0);
        }
        return b.flip();
    }
    public static void main(String[] args) {
        for(int packetSize:new int[]{256,128}) for(int jitter:new int[]{0,3,8,15}) {
            var pending=new PriorityQueue<Delivery>(Comparator.comparingLong(Delivery::at));
            Random random=new Random(134);
            for(int seq=0;seq*packetSize<48000*5;seq++) {
                long at=Math.round((seq+1)*packetSize/48000.0*1e9)+1_000_000_000L;
                at+=(long)(random.nextDouble()*jitter*1e6);
                pending.add(new Delivery(at,seq,packet(seq,packetSize)));
            }
            PhoneMicBuffer receiver=new PhoneMicBuffer();receiver.controls(1,false,0);
            ArrayList<Double> pulseTimes=new ArrayList<>();boolean high=false; long steadyUnderruns=0;
            for(long now=1_000_000_000L;now<6_300_000_000L;now+=5_000_000) {
                while(!pending.isEmpty() && pending.peek().at<=now) {var d=pending.remove();receiver.push(d.bytes,d.at);}
                float[] output=new float[240];receiver.mix(output,now);
                if(now<=5_900_000_000L)steadyUnderruns=receiver.underruns;
                for(int i=0;i<output.length;i++) {
                    boolean next=output[i]>.1;
                    if(next&&!high) pulseTimes.add((now-1_000_000_000L)/1e6+i/48.0);
                    high=next;
                }
            }
            ArrayList<Double> delays=new ArrayList<>();
            for(double time:pulseTimes) {double delay=time%100;if(delay<80)delays.add(delay);}
            Collections.sort(delays);
            if (packetSize==128 && jitter==0 && !Arrays.asList(args).contains("--baseline")) {
                if (delays.get(delays.size()/2)>=20 || steadyUnderruns!=0)
                    throw new AssertionError("Clean receiver path must stay under 20 ms without dropouts");
            }
            System.out.printf(Locale.ROOT,"packet=%d jitter_ms=%d pulses=%d median_ms=%.2f p95_ms=%.2f underruns=%d discarded=%d%n",packetSize,jitter,pulseTimes.size(),delays.get(delays.size()/2),delays.get((int)(delays.size()*.95)),steadyUnderruns,receiver.discarded);
        }
    }
}
