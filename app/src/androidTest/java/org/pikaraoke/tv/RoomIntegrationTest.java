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
        // Suppress only the welcome overlay, which is tested manually with D-pad.
        context.getSharedPreferences("host", 0).edit().putBoolean("welcomeShown", true).commit();
        instrumentation.startActivitySync(new Intent(context, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        long deadline = System.currentTimeMillis() + 90000;
        while(System.currentTimeMillis() < deadline) {
            if (Python.isStarted() && Python.getInstance().getModule("android_runtime.bootstrap").callAttr("ready").toBoolean()) break;
            Thread.sleep(500);
        }
        assertTrue("Embedded server did not start", Python.isStarted());
        Thread.sleep(8000); // Allow the actual GeckoView player to connect.
        String report = Python.getInstance().getModule("device_checks").callAttr("run", context).toString();
        android.util.Log.i("PiKaraokeIntegration", report);
        assertTrue(report, report.contains("\"download_to_file\": true"));
    }
}
