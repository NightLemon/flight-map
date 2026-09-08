"""CLI routing for synthetic NASR research-layer bundles."""

from __future__ import annotations

import json
import re

import pytest
from flightmap_ingestion import cli
from flightmap_ingestion.cli import app
from typer.testing import CliRunner

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def normalized_cli_output(output: str) -> str:
    """Compare CLI text independently of Rich styling and newline convention."""
    return _ANSI_ESCAPE.sub("", output).replace("\r\n", "\n").replace("\r", "\n")


def bundle_manifest(tmp_path):
    path = tmp_path / "synthetic-bundle.json"
    path.write_text(json.dumps({"APT": "synthetic-sha"}), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "flags, message",
    [
        (["--all-layers"], "--all-layers requires --research"),
        (["--bundle-manifest", "manifest"], "--bundle-manifest requires --all-layers"),
        (
            ["--research", "--all-layers", "--asset-sha256", "a" * 64],
            "--asset-sha256 cannot be used",
        ),
    ],
)
def test_layer_flags_are_rejected_before_opening_repository(tmp_path, flags, message):
    directory = tmp_path / "must-not-initialize"
    manifest = bundle_manifest(tmp_path)
    args = [str(manifest) if flag == "manifest" else flag for flag in flags]

    result = CliRunner().invoke(
        app, ["update", "--product", "nasr", "--data-dir", str(directory), *args]
    )

    assert result.exit_code == 2
    assert message in normalized_cli_output(result.output)
    assert not directory.exists()


def test_all_layers_without_manifest_routes_to_bundle_acquisition(tmp_path, monkeypatch):
    calls = []

    monkeypatch.setattr(cli, "_product", lambda *_: "synthetic-nasr")
    monkeypatch.setattr(cli, "Repository", lambda *_: "synthetic-repository")
    monkeypatch.setattr(
        cli,
        "_operation",
        lambda repository, product, operation, *, research=False: calls.append(
            (repository, product, research, operation())
        ),
    )
    monkeypatch.setattr(
        cli,
        "update_research_layers",
        lambda repository, product, *, preview=False: {
            "route": "acquire", "repository": repository, "product": product, "preview": preview
        },
    )
    monkeypatch.setattr(
        cli,
        "build_research_layers_from_assets",
        lambda *_args, **_kwargs: pytest.fail("Unexpected manifest build"),
    )

    result = CliRunner().invoke(
        app,
        ["update", "--product", "nasr", "--research", "--all-layers", "--data-dir", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert calls == [
        ("synthetic-repository", "nasr", True, {
            "route": "acquire",
            "repository": "synthetic-repository",
            "product": "synthetic-nasr",
            "preview": False,
        })
    ]


def test_all_layers_with_manifest_routes_raw_json_to_bundle_builder(tmp_path, monkeypatch):
    calls = []
    manifest = bundle_manifest(tmp_path)

    monkeypatch.setattr(cli, "_product", lambda *_: "synthetic-nasr")
    monkeypatch.setattr(cli, "Repository", lambda *_: "synthetic-repository")
    monkeypatch.setattr(
        cli,
        "_operation",
        lambda repository, product, operation, *, research=False: calls.append(
            (repository, product, research, operation())
        ),
    )
    monkeypatch.setattr(
        cli,
        "update_research_layers",
        lambda *_args, **_kwargs: pytest.fail("Unexpected online acquisition"),
    )
    monkeypatch.setattr(
        cli,
        "build_research_layers_from_assets",
        lambda repository, product, assets, *, preview=False: {
            "route": "manifest",
            "repository": repository,
            "product": product,
            "assets": assets,
            "preview": preview,
        },
    )

    result = CliRunner().invoke(
        app,
        [
            "update", "--product", "nasr", "--research", "--all-layers", "--bundle-manifest",
            str(manifest), "--preview", "--data-dir", str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls == [
        ("synthetic-repository", "nasr", True, {
            "route": "manifest", "repository": "synthetic-repository", "product": "synthetic-nasr",
            "assets": {"APT": "synthetic-sha"}, "preview": True,
        })
    ]
