from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def file_signature(path: Path) -> dict[str, str | int]:
    stat = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "source_hash": digest.hexdigest(),
        "source_size": stat.st_size,
        "source_mtime": str(stat.st_mtime_ns),
    }


def record_file_signature(meta: Any, path: Path) -> None:
    signature = file_signature(path)
    meta.source_hash = str(signature["source_hash"])
    meta.source_size = int(signature["source_size"])
    meta.source_mtime = str(signature["source_mtime"])
