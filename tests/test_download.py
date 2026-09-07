import zipfile
from pathlib import Path

import pytest
from flightmap_ingestion.download import AssetVerificationError, verify_download


def test_valid_zip_has_stable_sha(tmp_path: Path) -> None:
    asset = tmp_path / "asset.zip"
    with zipfile.ZipFile(asset, "w") as archive:
        archive.writestr("README.txt", "official fixture")

    first = verify_download(asset, "application/zip", require_zip=True)
    second = verify_download(asset, "application/octet-stream", require_zip=True)

    assert first == second
    assert len(first[0]) == 64
    assert first[1] > 0


def test_html_error_page_is_rejected(tmp_path: Path) -> None:
    asset = tmp_path / "not-data.zip"
    asset.write_text("<!doctype html><title>Access denied</title>", encoding="utf-8")

    with pytest.raises(AssetVerificationError, match="HTML"):
        verify_download(asset, "application/octet-stream", require_zip=True)


def test_non_zip_is_rejected_when_zip_required(tmp_path: Path) -> None:
    asset = tmp_path / "asset.zip"
    asset.write_bytes(b"not a zip")

    with pytest.raises(AssetVerificationError, match="ZIP"):
        verify_download(asset, "application/octet-stream", require_zip=True)
