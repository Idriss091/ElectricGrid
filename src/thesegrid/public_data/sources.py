from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LocalSourceManifest:
    path: Path
    source_type: str
    available: bool
    size_bytes: int
    sha256: str
    error: str = ""


def local_source_manifest(path: Path, source_type: str) -> LocalSourceManifest:
    if not path.exists():
        return LocalSourceManifest(
            path=path,
            source_type=source_type,
            available=False,
            size_bytes=0,
            sha256="",
            error=f"missing local source: {path}",
        )
    payload = path.read_bytes()
    return LocalSourceManifest(
        path=path,
        source_type=source_type,
        available=True,
        size_bytes=path.stat().st_size,
        sha256=hashlib.sha256(payload).hexdigest(),
    )
