"""On-device integration checks; never packaged in release APKs."""
import functools
import http.server
import json
from pathlib import Path
import subprocess
import threading
import time

import requests
from android_runtime import bootstrap


def run(context):
    assert bootstrap.ready(), bootstrap.status()
    k = bootstrap._backend.app.config['KARAOKE_INSTANCE']
    root = 'http://127.0.0.1:5555'
    guest = requests.Session()
    host = requests.Session()
    assert guest.get(root + '/api/auth').json()['password_required']
    assert guest.post(root + '/api/skip').status_code == 403
    password = str(context.getSharedPreferences('host', 0).getString('initialPassword', ''))
    assert host.post(root + '/api/auth', json={'admin_password': password}).status_code == 200
    for path in ['/', '/splash', '/browse', '/queue', '/search', '/info', '/settings', '/history', '/sessions', '/rankings']:
        response = host.get(root + path)
        assert response.status_code == 200, (path, response.status_code, response.text[:200])

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
            if state.get('now_playing_position', 0) > 2:
                break
            time.sleep(.5)
        assert state.get('now_playing_position', 0) > 2, state
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
        return json.dumps({'download_to_file': True, 'tv_browser_playback_position': state['now_playing_position'],
                           'phone_api_and_auth': True, 'pitch_and_normalization': True,
                           'ytdlp': ytdlp_version, 'upstream': str(k.ffmpeg_version)})
    finally:
        server.shutdown()

