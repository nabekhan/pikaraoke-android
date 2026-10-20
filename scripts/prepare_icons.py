#!/usr/bin/env python3
"""Use the original PiKaraoke app icon without changing its artwork."""
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT / "upstream/pikaraoke/static/icons/logo.ico"
    data = source.read_bytes()
    reserved, kind, count = struct.unpack_from("<HHH", data)
    assert reserved == 0 and kind == 1 and count > 0, "Invalid upstream icon"
    directory_end = 6 + count * 16
    assert directory_end <= len(data)
    candidates = []
    for index in range(count):
        length, offset = struct.unpack_from("<II", data, 6 + index * 16 + 8)
        assert offset >= directory_end and offset + length <= len(data)
        png = data[offset:offset + length]
        if png.startswith(b"\x89PNG\r\n\x1a\n"):
            width, height = struct.unpack_from(">II", png, 16)
            assert width == height and width > 0, "Upstream app icon must be square"
            candidates.append((width, png))
    assert candidates, "Upstream icon no longer contains a PNG; review required"
    width, png = max(candidates, key=lambda candidate: candidate[0])
    destination = ROOT / "app/build/generated/branding/res/drawable-nodpi/icon.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(png)
    print(f"Prepared original PiKaraoke icon ({width} x {width})")


if __name__ == "__main__":
    main()
