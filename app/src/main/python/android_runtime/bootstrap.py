"""Start the real PiKaraoke application entirely inside the APK."""
import logging
import functools
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import signal
import shutil
import stat
import zipfile

_backend = None
_context = None
_status = 'Starting PiKaraoke…'
_error = None
_processes = set()
_process_lock = threading.Lock()
_preferences_lock = threading.RLock()


def status():
    return _error or _status


def ready():
    from android_runtime import compat
    return _error is None and compat.servers_ready and _backend is not None and 'KARAOKE_INSTANCE' in _backend.app.config


def install_process_adapter(context):
    """Run the packaged executable libraries, with child-only runtime settings.

    Android 10+ disallows executing code from writable app data. These binaries
    are installed/extracted by the package manager into nativeLibraryDir.
    """
    native = Path(str(context.getApplicationInfo().nativeLibraryDir))
    base = Path(str(context.getNoBackupFilesDir())) / 'youtubedl-android'
    packages = base / 'packages'
    ytdlp = base / 'yt-dlp/yt-dlp'
    pythonhome = packages / 'python/usr'
    ldpath = ':'.join(str(packages / name / 'usr/lib') for name in ('python', 'ffmpeg', 'aria2c'))
    original = subprocess.Popen

    class AndroidPopen(original):
        def __init__(self, args, *pos, **kw):
            command = list(args) if isinstance(args, (list, tuple)) else args
            if isinstance(command, list) and command:
                name = str(command[0])
                is_ytdlp = len(command) >= 3 and command[1:3] == ['-m', 'yt_dlp']
                is_media = name in ('ffmpeg', 'ffprobe', 'quickjs')
                if is_ytdlp or is_media:
                    kw.setdefault('start_new_session', True)
                    env = dict(kw.get('env') or os.environ)
                    env['LD_LIBRARY_PATH'] = ldpath
                    env['TMPDIR'] = str(context.getCacheDir())
                    if is_ytdlp:
                        command = [str(native / 'libpython.so'), str(ytdlp),
                                   '--ffmpeg-location', str(native / 'libffmpeg.so'),
                                   '--js-runtimes', f'quickjs:{native / "libqjs.so"}',
                                   *command[3:]]
                        env['PYTHONHOME'] = str(pythonhome)
                        env['SSL_CERT_FILE'] = str(pythonhome / 'etc/tls/cert.pem')
                        env.pop('PYTHONPATH', None)
                    else:
                        command[0] = str(native / {'ffmpeg':'libffmpeg.so', 'ffprobe':'libffprobe.so', 'quickjs':'libqjs.so'}[name])
                    kw['env'] = env
            super().__init__(command, *pos, **kw)
            with _process_lock:
                _processes.difference_update(p for p in tuple(_processes) if p.poll() is not None)
                _processes.add(self)

    subprocess.Popen = AndroidPopen


def repair_native_cache(context):
    """Recover an extraction interrupted by device power loss, before init."""
    native = Path(str(context.getApplicationInfo().nativeLibraryDir))
    base = Path(str(context.getNoBackupFilesDir())) / 'youtubedl-android/packages'
    for name in ('python', 'ffmpeg'):
        directory = base / name
        if not directory.exists():
            continue
        with zipfile.ZipFile(native / f'lib{name}.zip.so') as archive:
            for entry in archive.infolist():
                if entry.is_dir() or stat.S_ISLNK(entry.external_attr >> 16):
                    continue
                file = directory / entry.filename
                if not file.is_file() or file.stat().st_size != entry.file_size:
                    logging.warning('Repairing incomplete native %s runtime', name)
                    shutil.rmtree(directory)
                    break


def start(context, songs_path):
    global _backend, _context, _status, _error
    _context = context
    normal_exit = False
    try:
        # Do not change HOME: Chaquopy owns it. Explicitly locate persisted data
        # before any upstream module captures get_data_directory by value.
        data = Path(str(context.getFilesDir())) / 'pikaraoke'
        data.mkdir(parents=True, exist_ok=True)
        Path(songs_path).mkdir(parents=True, exist_ok=True)
        from pikaraoke.lib import get_platform
        get_platform.get_data_directory = lambda: str(data)
        from com.yausername.youtubedl_android import YoutubeDL
        from com.yausername.ffmpeg import FFmpeg
        repair_native_cache(context)
        YoutubeDL.getInstance().init(context)
        FFmpeg.getInstance().init(context)
        install_process_adapter(context)
        cache = str(context.getCacheDir())
        os.environ['TMPDIR'] = cache
        tempfile.tempdir = cache
        from pikaraoke.lib import network, ffmpeg, youtube_dl
        from org.pikaraoke.tv import AndroidPlatform
        network.get_ip = lambda platform: str(AndroidPlatform.localIp(context))
        get_platform.get_installed_js_runtime = lambda: 'quickjs'
        youtube_dl.get_installed_js_runtime = get_platform.get_installed_js_runtime
        # The subprocess adapter provides the exact executable path. A second
        # bare "quickjs" option would overwrite that path in yt-dlp's parser.
        youtube_dl._js_runtime_args = lambda: []
        ffmpeg.supports_hardware_h264_encoding = lambda: False

        def update_ytdlp():
            from java import jclass
            channel = jclass('com.yausername.youtubedl_android.YoutubeDL$UpdateChannel')._STABLE
            YoutubeDL.getInstance().updateYoutubeDL(context, channel)
            return youtube_dl.get_youtubedl_version()
        youtube_dl.upgrade_youtubedl = update_ytdlp
        from pikaraoke.lib.preference_manager import PreferenceManager
        # Older APKs kept a display copy; passwords now live only in upstream's
        # hashed config storage. Removing the copy does not change that password.
        context.getSharedPreferences('host', 0).edit().remove('initialPassword').apply()
        # gevent made ordinary config-file operations indivisible. Preserve
        # that property when requests now run on separate Android threads.
        def locked(method):
            @functools.wraps(method)
            def call(*args, **kwargs):
                with _preferences_lock:
                    return method(*args, **kwargs)
            return call
        for name in ('get', 'get_or_default', 'set', 'clear', 'apply_all', 'reset_all'):
            setattr(PreferenceManager, name, locked(getattr(PreferenceManager, name)))
        from android_runtime.audio import install_audio_adapter
        install_audio_adapter(context)
        # Keep-awake is held by the foreground Android service and Activity.
        from pikaraoke.lib.keep_awake import KeepAwake
        KeepAwake.start = lambda self: None
        KeepAwake.stop = lambda self: None

        sys.argv = ['pikaraoke', '--port', '8080', '--headless', '--skip-ytdl-upgrade',
                    '--config-file-path', str(data / 'config.ini'),
                    '--download-path', str(songs_path), '--enable-mic-passthrough']
        # Upstream grants admin access while no password is configured, and
        # preserves any password already stored in this installation.
        from pikaraoke import app
        _backend = app
        app.compile_translations = lambda: None  # Compiled during APK build.
        from android_runtime.phone_mics import install as install_phone_mics
        install_phone_mics(app.app, context, lambda: AndroidPlatform.localIp(context))
        _status = 'Starting player…'
        app.main()
        normal_exit = True
    except SystemExit as exc:
        if exc.code not in (None, 0):
            logging.error('PiKaraoke startup exited with status %s', exc.code)
            _error = 'PiKaraoke could not start. Close and reopen the app.'
        else:
            _status = 'PiKaraoke stopped. Open the app to start again.'
            normal_exit = True
    except BaseException as exc:
        logging.exception('PiKaraoke startup failed')
        _error = f'PiKaraoke could not start: {type(exc).__name__}: {exc}'
    finally:
        from android_runtime.compat import stop_server
        stop_server()
        if normal_exit:
            _backend = None
            from org.pikaraoke.tv import KaraokeService
            if KaraokeService.instance is not None:
                KaraokeService.instance.stopSelf()


def stop():
    from android_runtime.phone_mics import stop as stop_phone_mics
    stop_phone_mics()
    if ready():
        _backend.app.config['KARAOKE_INSTANCE'].stop()
    from android_runtime.compat import stop_server
    stop_server()
    with _process_lock:
        for process in tuple(_processes):
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass


def refresh_library():
    if ready():
        k = _backend.app.config['KARAOKE_INSTANCE']
        k.sync_library()


def network_changed():
    if ready():
        from org.pikaraoke.tv import AndroidPlatform
        k = _backend.app.config['KARAOKE_INSTANCE']
        k.ip = str(AndroidPlatform.localIp(_context))
        k.url = f'http://{k.ip}:{k.port}'
        k.generate_qr_code()
        from android_runtime.phone_mics import refresh_certificate
        refresh_certificate()
        k.socketio.emit('android_network_changed', {'url': k.url})


def native_action(action):
    if not ready():
        return
    k = _backend.app.config['KARAOKE_INSTANCE']
    if action == 'pause':
        k.socketio.emit('resume' if k.playback_controller.is_paused else 'pause')
        k.playback_controller.pause()
    elif action == 'skip':
        k.socketio.emit('skip', 'TV remote')
        k.playback_controller.skip()
    elif action == 'restart': k.restart()


def set_host_password(password):
    if not ready():
        raise RuntimeError('The room is still starting')
    with _preferences_lock:
        _backend.app.config['ADMIN_AUTH'].set_password(password)
