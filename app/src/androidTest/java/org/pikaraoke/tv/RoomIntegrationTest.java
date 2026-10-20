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
    private static void screenshot(android.app.Instrumentation instrumentation, String name) throws java.io.IOException {
        // Gradle removes app storage after instrumentation. Keep captures in the
        // shell-owned test directory so the CI runner can retrieve them later.
        try (java.io.InputStream result = new android.os.ParcelFileDescriptor.AutoCloseInputStream(
                instrumentation.getUiAutomation().executeShellCommand(
                    "screencap -p /data/local/tmp/pikaraoke-tv-" + name + ".png"))) {
            byte[] buffer = new byte[1024];
            while (result.read(buffer) != -1) { }
        }
    }
    @Test public void standaloneRoomDownloadsAndPlays() throws Exception {
        android.app.Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        Context context = instrumentation.getTargetContext();
        if (android.os.Build.VERSION.SDK_INT >= 33)
            instrumentation.getUiAutomation().grantRuntimePermission(context.getPackageName(), android.Manifest.permission.POST_NOTIFICATIONS);
        context.getSharedPreferences("host", 0).edit().remove("welcomeShown").commit();
        if (!Python.isStarted()) {
            com.chaquo.python.android.AndroidPlatform platform = new com.chaquo.python.android.AndroidPlatform(context);
            platform.redirectStdioToLogcat();
            Python.start(platform);
        }
        Python.getInstance().getModule("device_checks").callAttr("seed_storage_quota", context);
        // Seed only this fresh instrumentation install. Cleanup must happen
        // before the server/library starts, and count unrelated retained files.
        java.io.File folder = AndroidPlatform.songs(context);
        java.io.File oldAudio = new java.io.File(folder, "quota-old.mp3");
        java.io.File oldGraphics = new java.io.File(folder, "quota-old.cdg");
        java.io.File retained = new java.io.File(folder, ".quota-keep");
        android.app.Activity activity = instrumentation.startActivitySync(new Intent(context, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        long deadline = System.currentTimeMillis() + 90000;
        while(System.currentTimeMillis() < deadline) {
            if (Python.isStarted() && Python.getInstance().getModule("android_runtime.bootstrap").callAttr("ready").toBoolean()) break;
            if (Python.isStarted() && Python.getInstance().getModule("android_runtime.bootstrap").callAttr("status").toString().contains("could not start")) break;
            Thread.sleep(500);
        }
        assertTrue("Embedded server did not start", Python.isStarted());
        assertTrue(Python.getInstance().getModule("android_runtime.bootstrap").callAttr("status").toString(),
            Python.getInstance().getModule("android_runtime.bootstrap").callAttr("ready").toBoolean());
        assertFalse("Old audio was not pruned at startup", oldAudio.exists());
        assertFalse("CDG companion was not pruned with its audio", oldGraphics.exists());
        assertTrue("Unrelated file was removed", retained.exists());
        Thread.sleep(8000); // Allow the actual GeckoView player to connect.
        instrumentation.runOnMainSync(() -> {
            android.view.View player = activity.findViewById(android.R.id.content).findViewWithTag("pikaraoke-player");
            assertNotNull("Player was not created automatically", player);
            assertTrue("First boot did not show the player", player.isShown());
            assertTrue("A first-boot prompt is covering the player", activity.hasWindowFocus());
            assertTrue("Player did not receive focus automatically", player.hasFocus());
        });
        screenshot(instrumentation, "room");
        String report = Python.getInstance().getModule("device_checks").callAttr("run", context).toString();
        screenshot(instrumentation, "playing");
        android.util.Log.i("PiKaraokeIntegration", report);
        assertTrue(report, report.contains("\"download_to_file\": true"));
        assertTrue(report, report.contains("\"song_storage_startup_and_settings\": true"));
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
