"""On-device integration checks; never packaged in release APKs."""
import functools
import http.server
import json
from pathlib import Path
import subprocess
import threading
import time
import ssl
import os

import requests
from android_runtime import bootstrap


def seed_storage_quota(context):
    """Fresh instrumentation data: remove 100% of a previously indexed library."""
    from org.pikaraoke.tv import AndroidPlatform
    from pikaraoke.lib import get_platform
    data = Path(str(context.getFilesDir())) / 'pikaraoke'
    data.mkdir(parents=True, exist_ok=True)
    get_platform.get_data_directory = lambda: str(data)
    from pikaraoke.lib.karaoke_database import KaraokeDatabase
    from pikaraoke.lib.song_storage import PREFERENCE
    songs = Path(str(AndroidPlatform.songs(context)))
    for name, size in [('quota-old.mp3', 256), ('quota-old.cdg', 128),
                       ('quota-second.mp4', 256), ('quota-third.zip', 256), ('.quota-keep', 128)]:
        file = songs / name
        file.write_bytes(b'x' * size)
        os.utime(file, (1, 1))
    (data / 'config.ini').write_text('[USERPREFERENCES]\n' + PREFERENCE + '=128\n')
    database = KaraokeDatabase(str(data / 'pikaraoke.db'))
    try:
        database.insert_songs([{'file_path': str(songs / name), 'youtube_id': None, 'format': extension}
            for name, extension in [('quota-old.mp3', 'cdg'), ('quota-second.mp4', 'mp4'), ('quota-third.zip', 'zip')]])
        assert len(database.get_all_song_paths()) == 3
    finally:
        database.close()


def check_phone_microphones(context, guest, host, root):
    ca = Path(str(context.getNoBackupFilesDir())) / 'phone-mic-tls/ca.crt'
    trusted = Path(str(context.getCacheDir())) / 'qa-mic-ca.pem'
    trusted.write_text(ssl.DER_cert_to_PEM_cert(ca.read_bytes()))
    secure = 'https://127.0.0.1:8444'
    tokens = []
    try:
        for path in ['/mic', '/static/phone-mic.js', '/static/phone-mic-worklet.js', '/static/phone-mic.css']:
            assert guest.get(root + path, timeout=10).status_code == 200
            assert guest.get(secure + path, verify=str(trusted), timeout=10).status_code == 200
        assert guest.post(root + '/api/phone-mics', json={'name':'HTTP refused'}, timeout=10).status_code == 403
        assert guest.post(secure + '/api/phone-mics', json={'name':'Origin refused'},
                          headers={'Origin':'https://other.invalid'}, verify=str(trusted), timeout=10).status_code == 403
        assert guest.get(root + '/api/phone-mics', timeout=10).json()['max'] == 2
        setting = {'pref':'max_phone_mics', 'val':'4'}
        assert guest.post(root + '/api/change_preferences', data=setting, timeout=10).status_code == 403
        for invalid in ['0', '5', '2.5']:
            assert not host.post(root + '/api/change_preferences', data={**setting, 'val':invalid}, timeout=10).json()[0]
        for number in range(4):
            if number == 2:
                assert guest.post(secure + '/api/phone-mics', json={'name':'Third'}, verify=str(trusted), timeout=10).status_code == 409
                assert host.post(root + '/api/change_preferences', data=setting, timeout=10).json()[0]
            response = guest.post(secure + '/api/phone-mics', json={'name':f'Phone {number+1}'}, verify=str(trusted), timeout=10)
            assert response.status_code == 201, response.status_code
            tokens.append(response.json()['id'])
        assert guest.post(secure + '/api/phone-mics', json={'name':'Fifth'}, verify=str(trusted), timeout=10).status_code == 409
        state = guest.get(secure + '/api/phone-mics', verify=str(trusted), timeout=10)
        assert state.json()['max'] == 4
        assert len(state.json()['active']) == 4
        assert all(token not in state.text for token in tokens)
        assert guest.post(secure + '/api/phone-mics/' + tokens[0] + '/controls',
                          json={'gain':.4,'muted':True,'reverb':1}, verify=str(trusted), timeout=10).status_code == 200
        assert host.post(root + '/api/change_preferences', data={**setting, 'val':'1'}, timeout=10).json()[0]
        state = guest.get(root + '/api/phone-mics', timeout=10).json()
        assert state['max'] == 1 and len(state['active']) == 4
        assert guest.post(secure + '/api/phone-mics', json={'name':'Extra'}, verify=str(trusted), timeout=10).status_code == 409
    finally:
        for token in tokens:
            guest.delete(secure + '/api/phone-mics/' + token, verify=str(trusted), timeout=10)
        assert host.post(root + '/api/change_preferences', data={'pref':'max_phone_mics', 'val':'2'}, timeout=10).json()[0]
        trusted.unlink(missing_ok=True)


def run(context):
    assert bootstrap.ready(), bootstrap.status()
    k = bootstrap._backend.app.config['KARAOKE_INSTANCE']
    root = 'http://127.0.0.1:8080'
    guest = requests.Session()
    host = requests.Session()
    fresh = guest.get(root + '/api/auth').json()
    assert fresh['authenticated'] and not fresh['password_required']
    settings = guest.get(root + '/settings').text
    assert 'Enter the administrator password' not in settings
    assert 'id="song-storage-form"' in settings
    assert guest.post(root + '/api/change_preferences', data={'pref':'volume', 'val':'.85'}).json()[0]
    # Verify that adding a password restores the normal host/guest boundary.
    import secrets
    password = secrets.token_urlsafe(16)
    bootstrap.set_host_password(password)
    assert guest.get(root + '/api/auth').json()['password_required']
    assert guest.post(root + '/api/skip').status_code == 403
    assert host.post(root + '/api/auth', json={'admin_password': password}).status_code == 200
    from pikaraoke.lib import song_storage
    assert k.song_storage_cleanup['removed_files'] == 4
    assert k.song_storage_cleanup['after_bytes'] == 128
    assert not k.db.get_all_song_paths(), 'Pruned songs remain in the library database'
    assert not list(k.song_manager.songs), 'Pruned songs remain browseable'
    setting = {'pref': song_storage.PREFERENCE, 'val': '1'}
    assert guest.post(root + '/api/change_preferences', data=setting).status_code == 403
    probe = Path(k.download_path) / '.quota-live-probe'
    probe.write_bytes(b'keep until next start')
    try:
        assert host.post(root + '/api/change_preferences', data=setting).json()[0]
        assert probe.exists(), 'Saving a limit pruned files in the running room'
        assert not host.post(root + '/api/change_preferences', data={**setting, 'val': '-1'}).json()[0]
        assert k.preferences.get_or_default(song_storage.PREFERENCE) == 1
        assert host.post(root + '/api/change_preferences', data={**setting, 'val': '1500000000'}).json()[0]
        assert k.preferences.get_or_default(song_storage.PREFERENCE) == 1500000000
        from pikaraoke.lib.preference_manager import PreferenceManager
        assert PreferenceManager(k.preferences.config_file_path).get_or_default(song_storage.PREFERENCE) == 1500000000
        assert 'id="song-storage-form"' in host.get(root + '/settings').text
        assert 'id="song-storage-form"' not in guest.get(root + '/settings').text
        home = guest.get(root + '/').text
        assert 'id="phone-mic" class="navbar-item no-spa" href="/mic"' in home
        assert 'icon icon-mic-1' in home
        assert guest.get(root + '/mic').status_code == 200
    finally:
        probe.unlink(missing_ok=True)
    for path in ['/', '/splash', '/browse', '/queue', '/search', '/info', '/settings', '/history', '/sessions', '/rankings']:
        response = host.get(root + path)
        assert response.status_code == 200, (path, response.status_code, response.text[:200])

    check_phone_microphones(context, guest, host, root)

    filters = subprocess.check_output(['ffmpeg', '-hide_banner', '-filters']).decode()
    for name in ['rubberband', 'loudnorm']:
        assert name in filters, name
    codecs = subprocess.check_output(['ffmpeg', '-hide_banner', '-encoders']).decode()
    assert 'libx264' in codecs and 'aac' in codecs
    ytdlp_version = subprocess.check_output(['python', '-m', 'yt_dlp', '--version']).decode().strip()
    assert ytdlp_version
    assert subprocess.run(['quickjs', '-e', 'if (1+1!==2) throw Error("JS failed")']).returncode == 0

    source_dir = Path(str(context.getCacheDir())) / 'qa-source'
    source_dir.mkdir(exist_ok=True)
    sample = source_dir / 'Android-integration.mp4'
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i',
                    'testsrc=size=640x360:rate=25', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000',
                    '-t', '24', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', str(sample)], check=True, timeout=90)
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(source_dir)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    existing = set(Path(k.download_path).glob('*.mp4'))
    saved_download_args = k.download_manager._additional_ytdl_args
    # A direct HTTP fixture has no extractor-provided height metadata, unlike
    # YouTube. Override only its format selector through the supported option.
    k.download_manager._additional_ytdl_args = ((saved_download_args or '') + ' -f best').strip()
    try:
        assert guest.post(root + '/api/download', json={
            'song_url': f'http://127.0.0.1:{server.server_port}/{sample.name}',
            'song_added_by': 'Android integration', 'song_title': 'Android integration', 'queue': False,
        }).status_code == 200
        deadline = time.monotonic() + 90
        downloaded = set()
        while time.monotonic() < deadline:
            downloaded = set(Path(k.download_path).glob('*.mp4')) - existing
            if downloaded and not k.download_manager.active_download and not k.download_manager.pending_downloads:
                break
            time.sleep(.25)
        assert downloaded, k.download_manager.get_downloads_status()
        song = str(next(iter(downloaded)))
        probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', song]))
        assert float(probe['format']['duration']) >= 23
        assert guest.post(root + '/api/enqueue', data={'song_to_add': song, 'song_added_by': 'Android integration'}).status_code == 200
        # Require real browser beacons. Setting is_playing alone would pass even
        # with a broken TV browser, codec, autoplay policy or Socket.IO session.
        deadline = time.monotonic() + 50
        while time.monotonic() < deadline:
            state = guest.get(root + '/api/now_playing').json()
            if (state.get('now_playing_position') or 0) > 2:
                break
            time.sleep(.5)
        assert (state.get('now_playing_position') or 0) > 2, state
        assert host.post(root + '/api/pause').status_code == 200
        time.sleep(.5)
        assert k.playback_controller.is_paused
        assert host.post(root + '/api/pause').status_code == 200
        # Pitch processing must survive an actual ffmpeg run, not just -filters.
        pitched = source_dir / 'pitched.m4a'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', song, '-vn', '-af', 'rubberband=pitch=1.122462,loudnorm', '-t', '2', str(pitched)], check=True, timeout=30)
        assert pitched.stat().st_size > 1000
        stats = host.get(root + '/api/info/stats')
        assert stats.status_code == 200 and 'memory' in stats.json()
        # Clearing the password restores automatic admin access to a new phone.
        bootstrap.set_host_password('')
        fresh = requests.Session()
        auth = fresh.get(root + '/api/auth').json()
        assert auth['authenticated'] and not auth['password_required']
        settings = fresh.get(root + '/settings').text
        assert 'Enter the administrator password' not in settings
        assert 'id="song-storage-form"' in settings
        assert fresh.post(root + '/api/change_preferences', data={'pref':'volume', 'val':'.85'}).json()[0]
        from pikaraoke import VERSION
        return json.dumps({'download_to_file': True, 'tv_browser_playback_position': state['now_playing_position'],
                           'song_storage_startup_and_settings': True,
                           'blank_password_auto_admin': True,
                           'phone_api_and_auth': True, 'phone_mic_https_and_four_slots': True, 'pitch_and_normalization': True,
                           'ytdlp': ytdlp_version, 'ffmpeg': str(k.ffmpeg_version), 'pikaraoke': VERSION})
    finally:
        server.shutdown()
        k.download_manager._additional_ytdl_args = saved_download_args
