package org.pikaraoke.tv;

import android.content.*;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import com.chaquo.python.Python;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class RoomIntegrationTest {
    @Test public void standaloneRoomDownloadsAndPlays() throws Exception {
        android.app.Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        Context context = instrumentation.getTargetContext();
        if (android.os.Build.VERSION.SDK_INT >= 33)
            instrumentation.getUiAutomation().grantRuntimePermission(context.getPackageName(), android.Manifest.permission.POST_NOTIFICATIONS);
        // Suppress only the welcome overlay, which is tested manually with D-pad.
        context.getSharedPreferences("host", 0).edit().putBoolean("welcomeShown", true).commit();
        instrumentation.startActivitySync(new Intent(context, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        long deadline = System.currentTimeMillis() + 90000;
        while(System.currentTimeMillis() < deadline) {
            if (Python.isStarted() && Python.getInstance().getModule("android_runtime.bootstrap").callAttr("ready").toBoolean()) break;
            if (Python.isStarted() && Python.getInstance().getModule("android_runtime.bootstrap").callAttr("status").toString().contains("could not start")) break;
            Thread.sleep(500);
        }
        assertTrue("Embedded server did not start", Python.isStarted());
        assertTrue(Python.getInstance().getModule("android_runtime.bootstrap").callAttr("status").toString(),
            Python.getInstance().getModule("android_runtime.bootstrap").callAttr("ready").toBoolean());
        Thread.sleep(8000); // Allow the actual GeckoView player to connect.
        java.io.File screenshots = new java.io.File(context.getExternalFilesDir(null), "screenshots");
        screenshots.mkdirs();
        android.graphics.Bitmap screen = instrumentation.getUiAutomation().takeScreenshot();
        if (screen != null) {
            try (java.io.FileOutputStream out = new java.io.FileOutputStream(new java.io.File(screenshots, "tv-room.png"))) {
                screen.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, out);
            }
            screen.recycle();
        }
        String report = Python.getInstance().getModule("device_checks").callAttr("run", context).toString();
        android.util.Log.i("PiKaraokeIntegration", report);
        assertTrue(report, report.contains("\"download_to_file\": true"));
        android.net.Uri roots = android.provider.DocumentsContract.buildRootsUri("org.pikaraoke.tv.songs");
        try (android.database.Cursor cursor = context.getContentResolver().query(roots, new String[]{"title"}, null, null, null)) {
            assertNotNull(cursor); assertTrue(cursor.moveToFirst()); assertEquals("PiKaraoke songs", cursor.getString(0));
        }
        java.io.File[] songs = AndroidPlatform.songs(context).listFiles((dir,name) -> name.endsWith(".mp4"));
        assertNotNull(songs); assertTrue(songs.length > 0);
        android.net.Uri document = android.provider.DocumentsContract.buildDocumentUri("org.pikaraoke.tv.songs", songs[0].getName());
        try (java.io.InputStream stream = context.getContentResolver().openInputStream(document)) {
            assertNotNull(stream); byte[] buffer = new byte[1024]; assertTrue(stream.read(buffer) > 100);
        }
        android.net.Uri outside = android.provider.DocumentsContract.buildDocumentUri("org.pikaraoke.tv.songs", "../../../../files/pikaraoke/config.ini");
        try {
            java.io.InputStream invalid = context.getContentResolver().openInputStream(outside);
            if(invalid!=null) invalid.close();
            fail("Document provider allowed traversal outside the library");
        } catch(java.io.FileNotFoundException expected) { }
    }
}
