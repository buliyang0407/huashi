from __future__ import annotations

import zipfile
from pathlib import Path


class UnsafeZipError(Exception):
    """Raised when a ZIP member would escape the extraction directory."""


def _safe_destination(root: Path, member_name: str) -> Path:
    if member_name.startswith("/") or member_name.startswith("\\"):
        raise UnsafeZipError(f"Unsafe absolute ZIP path: {member_name}")
    destination = (root / member_name).resolve()
    root_resolved = root.resolve()
    if destination != root_resolved and root_resolved not in destination.parents:
        raise UnsafeZipError(f"Unsafe ZIP path traversal: {member_name}")
    return destination


def safe_extract_zip(zip_path: Path | str, destination: Path | str) -> list[str]:
    zip_path = Path(zip_path)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)

    extracted: list[str] = []
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            target = _safe_destination(destination, info.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as output:
                output.write(source.read())
            extracted.append(info.filename)
    return extracted

