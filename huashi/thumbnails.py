from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import quote


class ThumbnailError(ValueError):
    pass


SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


class ThumbnailService:
    def __init__(self, data_root: Path | str):
        self.data_root = Path(data_root).resolve()
        self.thumbnail_root = self.data_root / "thumbnails"

    def source_path(self, rel_path: str) -> Path:
        clean = str(rel_path or "").strip().lstrip("/")
        if not clean or clean.startswith("pose:") or clean.startswith("face:"):
            raise ThumbnailError("Unsupported thumbnail source")
        target = (self.data_root / clean).resolve()
        if target == self.data_root or self.data_root not in target.parents:
            raise ThumbnailError("Thumbnail source escapes data root")
        return target

    def version_for(self, rel_path: str) -> str:
        source = self.source_path(rel_path)
        stat = source.stat()
        return f"{stat.st_mtime_ns}-{stat.st_size}"

    def url_for(self, rel_path: str, size: int = 480, version: str | None = None) -> str:
        encoded = quote(str(rel_path or "").strip().lstrip("/"), safe="")
        suffix = f"?v={quote(version, safe='')}" if version else ""
        return f"/thumbs/{int(size)}/{encoded}{suffix}"

    def url_for_existing_source(self, rel_path: str, size: int = 480) -> str:
        source = self.source_path(rel_path)
        if source.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ThumbnailError("Unsupported thumbnail suffix")
        return self.url_for(rel_path, size=size, version=self.version_for(rel_path))

    def cache_path(self, rel_path: str, size: int = 480) -> Path:
        source = self.source_path(rel_path)
        stat = source.stat()
        digest = hashlib.sha256(
            f"{rel_path}|{stat.st_mtime_ns}|{stat.st_size}|{int(size)}|webp".encode("utf-8")
        ).hexdigest()
        return self.thumbnail_root / f"w{int(size)}" / f"{digest}.webp"

    def ensure(self, rel_path: str, size: int = 480) -> Path:
        source = self.source_path(rel_path)
        if source.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ThumbnailError("Unsupported thumbnail suffix")
        target = self.cache_path(rel_path, size=size)
        if target.exists():
            return target

        from PIL import Image, ImageOps

        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(".tmp")
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGB")
            image.thumbnail((int(size), int(size)))
            image.save(temp, format="WEBP", quality=78, method=4)
        temp.replace(target)
        return target
