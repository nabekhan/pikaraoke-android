#!/usr/bin/env python3
"""Copy the pinned upstream; apply checked, Android-only substitutions.

The submodule remains pristine. An incompatible upstream update fails the build
instead of silently producing an app with missing features.
"""
from pathlib import Path
import shutil
from babel.messages.pofile import read_po
from babel.messages.mofile import write_mo

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'app/build/generated/python/pikaraoke'


def replace(path, old, new):
    text = path.read_text()
    if text.count(old) != 1:
        raise RuntimeError(f'Upstream adapter conflict in {path.name}: {old!r}')
    path.write_text(text.replace(old, new))


def main():
    if DEST.exists():
        shutil.rmtree(DEST)
    shutil.copytree(ROOT / 'upstream/pikaraoke', DEST, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    replace(DEST / 'app.py', 'from gevent import monkey, spawn\n\nmonkey.patch_all()',
            'from android_runtime.compat import spawn')
    replace(DEST / 'app.py', 'from gevent.pywsgi import WSGIServer',
            'from android_runtime.compat import WSGIServer')
    replace(DEST / 'app.py', 'async_mode="gevent"', 'async_mode="threading"')
    replace(DEST / 'lib/download_manager.py', 'from gevent import Greenlet, spawn',
            'from android_runtime.compat import Greenlet, spawn')
    replace(DEST / 'templates/base.html', '</head>',
            '<script defer src="{{ url_for(\'static\', filename=\'android-tv.js\') }}"></script>\n</head>')
    shutil.copyfile(ROOT / 'app/src/main/assets/android-tv.js', DEST / 'static/android-tv.js')
    for path in DEST.rglob('*.po'):
        with path.open('rb') as inp, path.with_suffix('.mo').open('wb') as out:
            write_mo(out, read_po(inp))
    print('Prepared pinned PiKaraoke sources and translations')


if __name__ == '__main__':
    main()
