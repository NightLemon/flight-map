"""带完整性校验和内容寻址缓存的下载器。"""

from __future__ import annotations

import hashlib
import os
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx

USER_AGENT = "FlightMapResearch/0.1 (+https://github.com/; non-operational)"


class AssetVerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class VerifiedDownload:
    path: Path
    sha256: str
    size_bytes: int
    content_type: str
    final_url: str | None = None


def verify_download(path: Path, content_type: str, *, require_zip: bool) -> tuple[str, int]:
    size = path.stat().st_size
    if size == 0:
        raise AssetVerificationError("下载内容为空")

    with path.open("rb") as stream:
        prefix = stream.read(512).lstrip().lower()
    normalized_type = content_type.split(";", 1)[0].strip().lower()
    if normalized_type in {"text/html", "application/xhtml+xml"} or prefix.startswith(
        (b"<!doctype html", b"<html")
    ):
        raise AssetVerificationError("下载地址返回了 HTML，而不是数据资产")

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)

    if require_zip:
        if not zipfile.is_zipfile(path):
            raise AssetVerificationError("资产不是有效 ZIP 文件")
        with zipfile.ZipFile(path) as archive:
            corrupt_member = archive.testzip()
            if corrupt_member is not None:
                raise AssetVerificationError(f"ZIP 成员损坏：{corrupt_member}")

    return digest.hexdigest(), size


class AssetDownloader:
    def __init__(
        self,
        cache_dir: Path,
        *,
        timeout_seconds: float = 60,
        max_bytes: int = 2 * 1024 * 1024 * 1024,
    ) -> None:
        self.cache_dir = cache_dir
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        cache_dir.mkdir(parents=True, exist_ok=True)

    def acquire(self, url: str, *, require_zip: bool = False) -> VerifiedDownload:
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.cache_dir, delete=False) as temp:
                temp_path = Path(temp.name)
                with httpx.stream(
                    "GET",
                    url,
                    headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"},
                    timeout=self.timeout_seconds,
                    follow_redirects=True,
                ) as response:
                    response.raise_for_status()
                    final_url = str(response.url)
                    content_type = response.headers.get("content-type", "application/octet-stream")
                    total = 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > self.max_bytes:
                            raise AssetVerificationError("资产超过配置的大小上限")
                        temp.write(chunk)

            digest, size = verify_download(temp_path, content_type, require_zip=require_zip)
            extension = ".zip" if require_zip else ".bin"
            final_path = self.cache_dir / f"{digest}{extension}"
            if final_path.exists():
                temp_path.unlink()
            else:
                os.replace(temp_path, final_path)
            return VerifiedDownload(final_path, digest, size, content_type, final_url)
        except Exception:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()
            raise
