package org.pikaraoke.tv;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.net.Uri;
import android.os.*;
import android.provider.OpenableColumns;
import android.view.*;
import android.widget.*;
import java.io.*;
import java.net.*;
import java.nio.file.Files;
import java.util.concurrent.*;
import org.mozilla.geckoview.*;

/** The bundled browser renders upstream's player; guests use ordinary browsers. */
public final class MainActivity extends Activity {
    private static GeckoRuntime runtime;
    private GeckoSession playerSession, remoteSession;
    private GeckoView player, remote;
    private FrameLayout layout;
    private TextView status;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private boolean controller = false, opened = false, destroyed = false;
    private static final String ORIGIN = "http://127.0.0.1:8080";

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        getWindow().getDecorView().setSystemUiVisibility(5894);
        layout = new FrameLayout(this);
        layout.setBackgroundColor(0xff172b4d);
        status = new TextView(this);
        status.setText("Starting PiKaraoke…\nYour room will be ready in a moment.");
        status.setTextSize(24); status.setGravity(Gravity.CENTER); status.setTextColor(0xffffffff);
        layout.addView(status, new FrameLayout.LayoutParams(-1,-1));
        setContentView(layout);
        startForegroundService(new Intent(this, KaraokeService.class));
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 2);
        io.execute(this::waitForServer);
    }
    private void waitForServer() {
        for (int attempt = 0; attempt < 180 && !destroyed; attempt++) {
            try {
                HttpURLConnection c = (HttpURLConnection) new URL(ORIGIN + "/api/auth").openConnection();
                c.setConnectTimeout(800); c.setReadTimeout(800);
                int code = c.getResponseCode(); c.disconnect();
                if (code == 200) { handler.post(this::openRoom); return; }
            } catch (IOException ignored) { }
            KaraokeService service = KaraokeService.instance;
            if (service != null) {
                String text = service.status();
                handler.post(() -> status.setText(text + "\nPress Back for room options."));
                if (text.contains("could not start")) return;
            }
            try { Thread.sleep(500); } catch (InterruptedException e) { return; }
        }
        if (!destroyed) handler.post(() -> status.setText("The room is taking longer to start.\nPress Back to close and reopen PiKaraoke."));
    }
    private GeckoSession session() {
        GeckoSessionSettings settings = new GeckoSessionSettings.Builder()
            .userAgentMode(GeckoSessionSettings.USER_AGENT_MODE_DESKTOP)
            .viewportMode(GeckoSessionSettings.VIEWPORT_MODE_DESKTOP)
            .suspendMediaWhenInactive(false)
            .userAgentOverride("Mozilla/5.0 (X11; Linux aarch64; rv:158.0) Gecko/20100101 Firefox/158.0 PiKaraokeTV").build();
        GeckoSession s = new GeckoSession(settings);
        s.setContentDelegate(new GeckoSession.ContentDelegate() {
            @Override public void onFullScreen(GeckoSession session, boolean full) { getWindow().getDecorView().setSystemUiVisibility(5894); }
        });
        s.setPermissionDelegate(new GeckoSession.PermissionDelegate() {
            @Override public GeckoResult<Integer> onContentPermissionRequest(GeckoSession session, ContentPermission perm) {
                boolean local = perm.uri.equals(ORIGIN) || perm.uri.startsWith(ORIGIN + "/");
                boolean media = perm.permission == PERMISSION_AUTOPLAY_AUDIBLE || perm.permission == PERMISSION_AUTOPLAY_INAUDIBLE;
                return GeckoResult.fromValue(local && media ? ContentPermission.VALUE_ALLOW : ContentPermission.VALUE_DENY);
            }
        });
        s.setNavigationDelegate(new GeckoSession.NavigationDelegate() {
            @Override public GeckoResult<AllowOrDeny> onLoadRequest(GeckoSession session, LoadRequest request) {
                Uri uri = Uri.parse(request.uri);
                boolean local = "http".equals(uri.getScheme()) && "127.0.0.1".equals(uri.getHost()) && uri.getPort() == 8080;
                if (!local && request.uri.startsWith("http")) {
                    try { startActivity(new Intent(Intent.ACTION_VIEW, uri)); } catch (ActivityNotFoundException ignored) { }
                }
                return GeckoResult.fromValue(local || "about:blank".equals(request.uri) ? AllowOrDeny.ALLOW : AllowOrDeny.DENY);
            }
        });
        s.setPromptDelegate(new RoomPrompts(this));
        s.open(runtime);
        return s;
    }
    private void openRoom() {
        if (destroyed || opened) return;
        opened = true;
        if (runtime == null) runtime = GeckoRuntime.create(getApplicationContext(), new GeckoRuntimeSettings.Builder()
            .consoleOutput(true).build());
        player = new GeckoView(this);
        playerSession = session();
        player.setSession(playerSession);
        layout.addView(player, new FrameLayout.LayoutParams(-1,-1));
        playerSession.loadUri(ORIGIN + "/splash");
        player.requestFocus();
        status.setVisibility(View.GONE);
        String initial = getSharedPreferences("host", 0).getString("initialPassword", "");
        if (!getSharedPreferences("host", 0).getBoolean("welcomeShown", false)) {
            new AlertDialog.Builder(this).setTitle("Your karaoke room is ready")
                .setMessage("Connect phones to the same Wi-Fi, then scan the QR code.\n\nPress Back or Menu for room options.\n\nYour initial host password:\n" + initial + "\n\nChange it in the room settings.")
                .setPositiveButton("Start singing", (d,w) -> getSharedPreferences("host", 0).edit().putBoolean("welcomeShown", true).apply()).show();
        }
    }
    private void showRemote() {
        if (!opened) return;
        if (remote == null) {
            remote = new GeckoView(this);
            remoteSession = session(); remote.setSession(remoteSession);
            layout.addView(remote, new FrameLayout.LayoutParams(-1,-1));
            remoteSession.loadUri(ORIGIN);
        }
        controller = true; remote.setVisibility(View.VISIBLE); remote.requestFocus();
    }
    private void showPlayer() {
        controller = false;
        if (remote != null) remote.setVisibility(View.GONE);
        if (player != null) { playerSession.setActive(true); player.requestFocus(); }
    }
    private void menu() {
        String[] labels = {"Show player", "Browse and queue songs", "Pause or resume", "Skip song", "Import song files", "Open song files", "Host password", "Allow microphones", "Stop room and exit"};
        new AlertDialog.Builder(this).setTitle("PiKaraoke TV · " + AndroidPlatform.localIp(this) + ":8080")
            .setItems(labels, (dialog, index) -> {
                switch(index) {
                    case 0: showPlayer(); break;
                    case 1: showRemote(); break;
                    case 2: KaraokeService.call("native_action", "pause"); break;
                    case 3: KaraokeService.call("native_action", "skip"); break;
                    case 4: importFiles(); break;
                    case 5:
                        Intent files = new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("*/*").addCategory(Intent.CATEGORY_OPENABLE);
                        files.putExtra("android.provider.extra.INITIAL_URI", android.provider.DocumentsContract.buildRootUri("org.pikaraoke.tv.songs", "songs"));
                        try { startActivityForResult(files, 20); } catch(ActivityNotFoundException e) { fileHelp(); }
                        break;
                    case 6:
                        String password = getSharedPreferences("host", 0).getString("initialPassword", "");
                        new AlertDialog.Builder(this).setTitle("Host password")
                            .setMessage("Password set on this TV: " + password + "\n\nIf you changed it from a phone, use your new password. Host access is separate from your device password.")
                            .setPositiveButton("Close", null)
                            .setNeutralButton("Set host password", (d,w) -> changePassword()).show(); break;
                    case 7:
                        if (!AndroidAudio.hasPermission(this)) requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, 3);
                        else if (KaraokeService.instance != null) { KaraokeService.instance.enableMicrophoneForeground(); showRemote(); }
                        break;
                    case 8: stopService(new Intent(this, KaraokeService.class)); finishAndRemoveTask(); break;
                }
            }).setNegativeButton("Return to room", null).show();
    }
    private void fileHelp() {
        new AlertDialog.Builder(this).setTitle("Song files")
            .setMessage("Your songs are saved as files in:\n" + AndroidPlatform.songs(this) + "\n\nUse a file manager that supports Android document providers to copy files from PiKaraoke songs.")
            .setPositiveButton("Close", null).show();
    }
    private void changePassword() {
        EditText input = new EditText(this);
        input.setSingleLine();
        input.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD);
        AlertDialog dialog = new AlertDialog.Builder(this).setTitle("Set host password")
            .setMessage("Use at least 8 characters. Phones will need to sign in again for host controls.")
            .setView(input).setPositiveButton("Save password", null).setNegativeButton("Cancel", null).create();
        dialog.setOnShowListener(d -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            String password=input.getText().toString();
            if(password.length()<8) { input.setError("Use at least 8 characters"); return; }
            if(!opened || KaraokeService.instance==null) { input.setError("Open the room before changing its password"); return; }
            KaraokeService.call("set_host_password", password);
            dialog.dismiss();
        }));
        dialog.show();
    }
    private void importFiles() {
        Intent pick = new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("*/*").addCategory(Intent.CATEGORY_OPENABLE);
        pick.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
        try { startActivityForResult(pick, 10); }
        catch (ActivityNotFoundException e) { fileHelp(); }
    }
    @Override protected void onActivityResult(int request, int result, Intent intent) {
        super.onActivityResult(request, result, intent);
        if (request != 10 || result != RESULT_OK || intent == null) return;
        java.util.List<Uri> uris = new java.util.ArrayList<>();
        if (intent.getClipData() != null) for (int i=0; i<intent.getClipData().getItemCount(); i++) uris.add(intent.getClipData().getItemAt(i).getUri());
        else if (intent.getData() != null) uris.add(intent.getData());
        io.execute(() -> {
            int imported = 0;
            try {
                for (Uri uri : uris) {
                    String name = "song-" + System.nanoTime() + ".mp4";
                    try (Cursor cursor = getContentResolver().query(uri, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
                        if (cursor != null && cursor.moveToFirst()) name = cursor.getString(0);
                    }
                    if (name == null || !name.equals(new File(name).getName()) || name.equals(".") || name.equals("..")) throw new IOException("Choose a song file with a valid filename.");
                    File dest = new File(AndroidPlatform.songs(this), name);
                    if (dest.exists()) throw new IOException("A file with that name already exists: " + name);
                    File temp = File.createTempFile("import-", ".part", AndroidPlatform.songs(this));
                    try {
                        try (InputStream in = getContentResolver().openInputStream(uri); OutputStream out = new FileOutputStream(temp)) {
                            if (in == null) throw new IOException("Cannot read file");
                            byte[] buffer = new byte[65536]; int count;
                            while ((count = in.read(buffer)) != -1) out.write(buffer, 0, count);
                        }
                        Files.move(temp.toPath(), dest.toPath()); imported++;
                    } finally { temp.delete(); }
                }
                final int count = imported;
                handler.post(() -> Toast.makeText(this, count + " song files imported", Toast.LENGTH_LONG).show());
            } catch (IOException e) {
                handler.post(() -> new AlertDialog.Builder(this).setTitle("Could not import every file").setMessage(e.getMessage()).setPositiveButton("Close", null).show());
            } finally { KaraokeService.call("refresh_library"); }
        });
    }
    @Override public void onRequestPermissionsResult(int code, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(code, permissions, results);
        if (code == 3 && results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED && KaraokeService.instance != null)
            KaraokeService.instance.enableMicrophoneForeground();
    }
    @Override public boolean onKeyDown(int key, KeyEvent event) {
        if (key == KeyEvent.KEYCODE_BACK || key == KeyEvent.KEYCODE_MENU || (!controller && key == KeyEvent.KEYCODE_DPAD_CENTER)) { menu(); return true; }
        if (key == KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE) { KaraokeService.call("native_action", "pause"); return true; }
        if (key == KeyEvent.KEYCODE_MEDIA_NEXT) { KaraokeService.call("native_action", "skip"); return true; }
        return super.onKeyDown(key, event);
    }
    @Override protected void onDestroy() {
        destroyed = true; handler.removeCallbacksAndMessages(null); io.shutdownNow();
        if (playerSession != null) playerSession.close();
        if (remoteSession != null) remoteSession.close();
        super.onDestroy();
    }
}
