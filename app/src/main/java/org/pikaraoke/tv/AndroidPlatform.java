package org.pikaraoke.tv;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.LinkAddress;
import android.net.LinkProperties;
import android.net.Network;
import android.net.NetworkCapabilities;
import java.io.File;
import java.net.Inet4Address;

public final class AndroidPlatform {
    private AndroidPlatform() {}
    public static File songs(Context context) {
        File base = context.getExternalFilesDir(null);
        File dir = new File(base != null ? base : context.getFilesDir(), "songs");
        dir.mkdirs();
        return dir;
    }
    public static String localIp(Context context) {
        ConnectivityManager cm = context.getSystemService(ConnectivityManager.class);
        String selected = "127.0.0.1"; int priority = -1;
        for (Network network : cm.getAllNetworks()) {
            NetworkCapabilities caps = cm.getNetworkCapabilities(network);
            if (caps == null) continue;
            int score = caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) ? 2 :
                caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) ? 1 : -1;
            if (score < 0 || score <= priority) continue;
            LinkProperties links = cm.getLinkProperties(network);
            if (links != null) for (LinkAddress addr : links.getLinkAddresses()) {
                if (addr.getAddress() instanceof Inet4Address && !addr.getAddress().isLoopbackAddress() && !addr.getAddress().isLinkLocalAddress()) {
                    selected = addr.getAddress().getHostAddress(); priority = score; break;
                }
            }
        }
        return selected;
    }
}
