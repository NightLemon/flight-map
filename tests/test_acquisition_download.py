from pathlib import Path

import httpx
import pytest
from flightmap_ingestion.download import AssetDownloader, AssetVerificationError, verify_download


def test_verification_does_not_read_entire_file_at_once(tmp_path, monkeypatch):
    path = tmp_path / "asset"
    path.write_bytes(b"a" * 4096)
    monkeypatch.setattr(Path, "read_bytes", lambda self: pytest.fail("unbounded read"))
    assert verify_download(path, "text/plain", require_zip=False)[1] == 4096


def test_download_limit_removes_temporary_file(tmp_path, monkeypatch):
    response = httpx.Response(
        200, content=b"too large", request=httpx.Request("GET", "https://faa.gov/x")
    )

    class Stream:
        def __enter__(self):
            return response

        def __exit__(self, *_):
            response.close()

    monkeypatch.setattr(httpx, "stream", lambda *args, **kwargs: Stream())
    with pytest.raises(AssetVerificationError, match="上限"):
        AssetDownloader(tmp_path, max_bytes=3).acquire("https://faa.gov/x")
    assert list(tmp_path.iterdir()) == []
