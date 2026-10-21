"""Startup-only cleanup for a configured song folder storage limit."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Iterable

PREFERENCE = "max_song_storage_bytes"
MAX_BYTES = 2**53 - 1  # Also exactly representable by JavaScript.
COMPANIONS = {".cdg", ".mcg", ".ass"}


def cleanup_journal_path(data_directory: str, songs_path: str) -> str:
    """Keep cleanup intents separate for each configured song folder."""
    identity = hashlib.sha256(os.fsencode(os.path.abspath(songs_path))).hexdigest()
    return os.path.join(data_directory, f"song-cleanup-{identity}.json")


def _supports_descriptor_traversal() -> bool:
    """Require the POSIX primitives that keep a changed path inside the root."""
    return (
        hasattr(os, "fwalk")
        and hasattr(os, "O_DIRECTORY")
        and hasattr(os, "O_NOFOLLOW")
        and os.open in os.supports_dir_fd
    )


def parse_limit(value: object) -> int:
    """Return a non-negative integer byte limit, rejecting coercions."""
    text = str(value).strip()
    if not re.fullmatch(r"[0-9]{1,16}", text) or int(text) > MAX_BYTES:
        raise ValueError("Invalid song storage limit")
    return int(text)


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _scan(
    root_fd: int, media_extensions: set[str]
) -> tuple[int, list[tuple[tuple[tuple[str, ...], str], list[tuple[str, os.stat_result]]]]]:
    total = 0
    groups: dict[tuple[tuple[str, ...], str], list[tuple[str, os.stat_result]]] = {}

    def scan_error(error: OSError) -> None:
        raise error

    for directory, _, names, directory_fd in os.fwalk(
        ".", dir_fd=root_fd, follow_symlinks=False, onerror=scan_error
    ):
        parts = Path(directory).parts
        for name in names:
            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                continue
            total += info.st_size
            file = Path(name)
            if any(part.startswith(".") for part in (*parts, name)):
                continue
            if file.suffix.lower() in media_extensions | COMPANIONS:
                groups.setdefault((parts, file.stem.lower()), []).append((name, info))

    songs = [
        (key, files)
        for key, files in groups.items()
        if any(Path(name).suffix.lower() in media_extensions for name, _ in files)
    ]
    songs.sort(key=lambda song: (max(info.st_mtime_ns for _, info in song[1]), song[0]))
    return total, songs


def _open_directory(root_fd: int, parts: Iterable[str]) -> int:
    current = os.dup(root_fd)
    try:
        for part in parts:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            os.close(current)
            current = next_fd
        return current
    except BaseException:
        os.close(current)
        raise


def _read_journal(
    songs_path: str | os.PathLike[str], journal_path: str | os.PathLike[str]
) -> set[str]:
    try:
        data = json.loads(Path(journal_path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return set()
    except ValueError as error:
        raise OSError("Invalid song cleanup journal") from error

    if (
        not isinstance(data, dict)
        or data.get("root") != os.path.abspath(songs_path)
        or not isinstance(data.get("paths"), list)
    ):
        raise OSError("Song cleanup journal does not match this folder")
    paths = data["paths"]
    if any(
        not isinstance(path, str)
        or not Path(path).parts
        or Path(path).is_absolute()
        or ".." in Path(path).parts
        for path in paths
    ):
        raise OSError("Invalid song cleanup journal path")
    return set(paths)


def _record_intent(
    songs_path: str | os.PathLike[str],
    journal_path: str | os.PathLike[str],
    songs: list[tuple[tuple[tuple[str, ...], str], list[tuple[str, os.stat_result]]]],
    media_extensions: set[str],
) -> None:
    paths = _read_journal(songs_path, journal_path)
    for (parts, _), files in songs:
        paths.update(
            str(Path(*parts, name))
            for name, _ in files
            if Path(name).suffix.lower() in media_extensions
        )
    journal = Path(journal_path)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=journal.parent, delete=False, encoding="utf-8"
        ) as out:
            temporary = Path(out.name)
            json.dump({"root": os.path.abspath(songs_path), "paths": sorted(paths)}, out)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, journal)
        directory_fd = os.open(journal.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def reconcile_journal(
    songs_path: str | os.PathLike[str], journal_path: str | os.PathLike[str], database: object
) -> int:
    """Remove DB rows for completed cleanup intents before the warm library load."""
    paths = _read_journal(songs_path, journal_path)
    if not paths:
        return 0
    if not _supports_descriptor_traversal():
        logging.warning("Song storage cleanup is unavailable on this platform")
        return 0
    root_fd = os.open(songs_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    missing: list[str] = []
    try:
        for path in paths:
            relative = Path(path)
            directory_fd = None
            try:
                directory_fd = _open_directory(root_fd, relative.parts[:-1])
                os.stat(relative.name, dir_fd=directory_fd, follow_symlinks=False)
            except FileNotFoundError:
                missing.append(str(Path(songs_path) / relative))
            finally:
                if directory_fd is not None:
                    os.close(directory_fd)
        database.delete_by_paths(missing)
        Path(journal_path).unlink(missing_ok=True)
    finally:
        os.close(root_fd)
    return len(missing)


def prune_songs(
    songs_path: str | os.PathLike[str],
    limit: object,
    media_extensions: Iterable[str],
    journal_path: str | os.PathLike[str] | None = None,
) -> dict[str, int | bool | None]:
    """Delete oldest complete song groups at startup, never while the app is live."""
    result: dict[str, int | bool | None] = {
        "limit_bytes": 0,
        "before_bytes": None,
        "after_bytes": None,
        "removed_files": 0,
        "removed_bytes": 0,
        "error": False,
    }
    try:
        limit = parse_limit(limit)
    except ValueError:
        logging.warning("Invalid song storage limit; no songs removed")
        return result
    result["limit_bytes"] = limit
    if limit == 0:
        return result
    if not _supports_descriptor_traversal():
        result["error"] = True
        logging.warning("Song storage cleanup is unavailable on this platform")
        return result

    root_fd: int | None = None
    extensions = {extension.lower() for extension in media_extensions}
    try:
        root_fd = os.open(songs_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        total, songs = _scan(root_fd, extensions)
        result.update(before_bytes=total, after_bytes=total)
        planned, remaining = [], total
        for song in songs:
            if remaining <= limit:
                break
            planned.append(song)
            remaining -= sum(info.st_size for _, info in song[1])
        if journal_path is not None and planned:
            _record_intent(songs_path, journal_path, planned, extensions)
        for (parts, _), files in planned:
            if result["after_bytes"] <= limit:
                break
            directory_fd = _open_directory(root_fd, parts)
            try:
                for name, original in files:
                    current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    if not stat.S_ISREG(current.st_mode) or _identity(current) != _identity(
                        original
                    ):
                        raise OSError("Song folder changed during startup cleanup")
                ordered = sorted(
                    files,
                    key=lambda file: (Path(file[0]).suffix.lower() not in extensions, file[0]),
                )
                for name, original in ordered:
                    current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    if _identity(current) != _identity(original):
                        raise OSError("Song folder changed during startup cleanup")
                    os.unlink(name, dir_fd=directory_fd)
                    result["removed_files"] += 1
                    result["removed_bytes"] += original.st_size
                    result["after_bytes"] -= original.st_size
            finally:
                os.close(directory_fd)
    except OSError:
        result["error"] = True
        logging.warning(
            "Song storage cleanup stopped; some files could not be removed", exc_info=True
        )
    finally:
        if root_fd is not None:
            os.close(root_fd)
    logging.info(
        "Song storage cleanup: removed %s files (%s bytes)",
        result["removed_files"],
        result["removed_bytes"],
    )
    return result
