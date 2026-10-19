#!/usr/bin/env python3
"""Archive tracked integration and pinned upstream files, excluding Git/caches."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

root = Path.cwd()
output = Path(sys.argv[1])
with tarfile.open(output, "w:gz", dereference=False) as archive:
    for folder, prefix in [(root, ""), (root / "upstream", "upstream/")]:
        files = subprocess.check_output(["git", "-C", str(folder), "ls-files", "-z"]).decode().split("\0")
        for name in files:
            path = folder / name
            if name and (path.is_file() or path.is_symlink()):
                archive.add(path, arcname="pikaraoke-tv/" + prefix + name, recursive=False)
    revision = json.dumps({
        "integration_base": subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip(),
        "upstream": subprocess.check_output(["git", "-C", "upstream", "rev-parse", "HEAD"]).decode().strip(),
    }, indent=2).encode()
    entry = tarfile.TarInfo("pikaraoke-tv/SOURCE-REVISION.json")
    entry.size = len(revision)
    archive.addfile(entry, io.BytesIO(revision))
