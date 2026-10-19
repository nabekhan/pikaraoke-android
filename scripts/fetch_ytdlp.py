#!/usr/bin/env python3
"""Verify the pinned yt-dlp zipapp, overriding the AAR's older raw resource."""
import hashlib
from pathlib import Path
import urllib.request

VERSION = '2026.08.19'
SHA256 = '1fa6733c37ea6fb51c99ad8fe785e7b7e5f3246c9b980230329d4fb72ed8d4d6'
ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'app/build/generated/ytdlp/res/raw/ytdlp'


def main():
    cache = ROOT / '.cache' / f'yt-dlp-{VERSION}'
    cache.parent.mkdir(exist_ok=True)
    if not cache.exists():
        urllib.request.urlretrieve(f'https://github.com/yt-dlp/yt-dlp/releases/download/{VERSION}/yt-dlp', cache)
    payload = cache.read_bytes()
    if hashlib.sha256(payload).hexdigest() != SHA256:
        raise RuntimeError('yt-dlp checksum mismatch; refusing to package')
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_bytes(payload)
    print(f'Verified yt-dlp {VERSION}')


if __name__ == '__main__':
    main()
