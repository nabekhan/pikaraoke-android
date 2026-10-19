package org.pikaraoke.tv;

import android.app.*;
import android.content.*;
import android.content.pm.ServiceInfo;
import android.net.*;
import android.os.*;
import android.util.Log;
import com.chaquo.python.*;
import com.chaquo.python.android.AndroidPlatform;
import java.util.concurrent.*;

public final class KaraokeService extends Service {
    public static volatile KaraokeService instance;
    private static final ExecutorService actions = Executors.newSingleThreadExecutor();
    private PowerManager.WakeLock wakeLock;
    private ConnectivityManager.NetworkCallback networkCallback;
    private volatile PyObject backend;
    public volatile String state = "Starting PiKaraoke…";

    @Override public void onCreate() {
        super.onCreate();
        instance = this;
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel("karaoke", "Karaoke room", NotificationManager.IMPORTANCE_LOW));
        Intent show = new Intent(this, MainActivity.class);
        PendingIntent open = PendingIntent.getActivity(this, 0, show, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification notification = new Notification.Builder(this, "karaoke")
            .setContentTitle("PiKaraoke room is running")
            .setContentText("Phones on your Wi-Fi can join. Open PiKaraoke to sing or stop the room.")
            .setSmallIcon(android.R.drawable.ic_media_play).setContentIntent(open).setOngoing(true).build();
        int serviceTypes = ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK;
        if (Build.VERSION.SDK_INT >= 30 && AndroidAudio.hasPermission(this)) serviceTypes |= ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE;
        if (Build.VERSION.SDK_INT >= 29) startForeground(1, notification, serviceTypes);
        else startForeground(1, notification);
        wakeLock = getSystemService(PowerManager.class).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "pikaraoke:room");
        wakeLock.acquire();
        networkCallback = new ConnectivityManager.NetworkCallback() {
            @Override public void onLinkPropertiesChanged(Network n, LinkProperties p) { call("network_changed"); }
            @Override public void onLost(Network n) { call("network_changed"); }
        };
        getSystemService(ConnectivityManager.class).registerNetworkCallback(new NetworkRequest.Builder()
            .clearCapabilities().addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
            .addTransportType(NetworkCapabilities.TRANSPORT_ETHERNET).build(), networkCallback);
        new Thread(() -> {
            try {
                if (!Python.isStarted()) Python.start(new AndroidPlatform(getApplicationContext()));
                backend = Python.getInstance().getModule("android_runtime.bootstrap");
                backend.callAttr("start", getApplicationContext(), org.pikaraoke.tv.AndroidPlatform.songs(this).getAbsolutePath());
                state = backend.callAttr("status").toString();
            } catch (Throwable e) {
                state = "PiKaraoke could not start. Close and reopen the app.";
                Log.e("PiKaraoke", "Backend failed", e);
            }
        }, "PiKaraoke server").start();
    }
    public static void call(String method, Object... args) {
        actions.execute(() -> {
            KaraokeService service = instance;
            if (service != null && service.backend != null) {
                try { service.backend.callAttr(method, args); }
                catch (Throwable e) { Log.e("PiKaraoke", "Action failed: " + method, e); }
            }
        });
    }
    public String status() {
        return backend != null ? backend.callAttr("status").toString() : state;
    }
    public void enableMicrophoneForeground() {
        if (Build.VERSION.SDK_INT >= 30 && AndroidAudio.hasPermission(this)) {
            Notification n = new Notification.Builder(this, "karaoke").setContentTitle("PiKaraoke room is running")
                .setContentText("Microphone passthrough is available in room settings.")
                .setSmallIcon(android.R.drawable.ic_media_play).setOngoing(true).build();
            startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK | ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE);
        }
    }
    @Override public int onStartCommand(Intent intent, int flags, int startId) { return START_NOT_STICKY; }
    @Override public IBinder onBind(Intent intent) { return null; }
    @Override public void onDestroy() {
        getSystemService(ConnectivityManager.class).unregisterNetworkCallback(networkCallback);
        AndroidAudio.stopAll();
        if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        instance = null;
        new Thread(() -> {
            try { if (backend != null) backend.callAttr("stop"); }
            finally { android.os.Process.killProcess(android.os.Process.myPid()); }
        }).start();
        super.onDestroy();
    }
}
