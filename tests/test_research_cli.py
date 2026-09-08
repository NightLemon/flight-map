import json

import pytest
from flightmap_ingestion.acquisition import build_local
from flightmap_ingestion.cli import app
from flightmap_ingestion.research_acquisition import build_research_from_asset
from flightmap_storage import Repository, StoreError
from test_acquisition_build import FIXTURES, manifest, product
from test_research_acquisition import FIXTURE, NOW, acquired, airport_zip, nasr_product
from typer.testing import CliRunner


def invoke(repository, *args):
    return CliRunner().invoke(app, [*args, "--data-dir", str(repository.data_dir)])


def test_research_report_activation_and_revocation_leave_dtpp_current_unchanged(tmp_path):
    repository = Repository(tmp_path / "data")
    dtpp = build_local(repository, product("dtpp"), FIXTURES / "dtpp_synthetic.xml", manifest())
    repository.promote(dtpp["release_id"], product("dtpp"), at=NOW)
    pointers = repository.snapshot()["pointers"]
    asset = acquired(repository, airport_zip(tmp_path))
    snapshot_id = build_research_from_asset(repository, nasr_product(), asset.sha256, at=NOW)[
        "snapshot_id"
    ]

    report = invoke(repository, "report", "--snapshot-id", snapshot_id)
    assert report.exit_code == 0, report.output
    response = json.loads(report.stdout)
    assert response["snapshot"]["id"] == snapshot_id
    assert response["snapshot"]["exact_validity_status"] == "unknown"
    assert response["report"]["input_count"] == response["report"]["success_count"] == 2
    assert response["inputs"][0]["sha256"] == asset.sha256
    assert response["inputs"][0]["source_id"] == "faa-aeronav"

    activate = invoke(repository, "activate-snapshot", "--snapshot-id", snapshot_id)
    assert activate.exit_code == 0, activate.output
    assert json.loads(activate.stdout)["status"] == "active"
    restarted = Repository(repository.data_dir)
    assert (
        restarted.resolve_snapshot(snapshot_id, nasr_product(), source_id="faa-aeronav", at=NOW).id
        == snapshot_id
    )

    promote = invoke(repository, "promote", "--release-id", snapshot_id)
    assert promote.exit_code == 1
    assert "unknown exact validity" in json.loads(promote.stdout)["error"]
    assert repository.snapshot()["pointers"] == pointers
    strict_report = invoke(repository, "report", "--release-id", dtpp["release_id"])
    assert strict_report.exit_code == 0
    assert json.loads(strict_report.stdout)["release"]["id"] == dtpp["release_id"]

    revoke = invoke(
        repository,
        "revoke-snapshot",
        "--snapshot-id",
        snapshot_id,
        "--reason",
        "Synthetic correction test",
    )
    assert revoke.exit_code == 0
    assert json.loads(revoke.stdout)["status"] == "revoked"
    with pytest.raises(StoreError) as exc:
        Repository(repository.data_dir).resolve_snapshot(
            snapshot_id, nasr_product(), source_id="faa-aeronav", at=NOW
        )
    assert exc.value.status_code == 410
    after = invoke(repository, "report", "--snapshot-id", snapshot_id)
    assert json.loads(after.stdout)["snapshot"]["revoked_reason"] == "Synthetic correction test"
    assert repository.snapshot()["pointers"] == pointers
    again = invoke(repository, "activate-snapshot", "--snapshot-id", snapshot_id)
    assert again.exit_code == 1
    assert "revoked" in json.loads(again.stdout)["error"]


@pytest.mark.parametrize("flags", [[], ["--release-id", "a", "--snapshot-id", "b"]])
def test_report_requires_one_identity_before_initializing_database(tmp_path, flags):
    directory = tmp_path / "must-not-initialize"
    response = CliRunner().invoke(app, ["report", *flags, "--data-dir", str(directory)])
    assert response.exit_code == 2
    assert "exactly one" in response.output
    assert not directory.exists()


def test_blocked_report_is_readable_and_failed_activation_keeps_previous_snapshot(tmp_path):
    repository = Repository(tmp_path / "data")
    valid_asset = acquired(repository, airport_zip(tmp_path))
    valid_id = build_research_from_asset(repository, nasr_product(), valid_asset.sha256, at=NOW)[
        "snapshot_id"
    ]
    assert invoke(repository, "activate-snapshot", "--snapshot-id", valid_id).exit_code == 0
    invalid_asset = acquired(
        repository,
        airport_zip(tmp_path, text=FIXTURE.read_text().replace("31.5,-85.25", "99,-85.25")),
    )
    invalid_id = build_research_from_asset(
        repository, nasr_product(), invalid_asset.sha256, at=NOW
    )["snapshot_id"]
    report = invoke(repository, "report", "--snapshot-id", invalid_id)
    assert report.exit_code == 0
    assert json.loads(report.stdout)["report"]["error_count"] == 1
    rejected = invoke(repository, "activate-snapshot", "--snapshot-id", invalid_id)
    assert rejected.exit_code == 1
    assert "blocks" in json.loads(rejected.stdout)["error"]
    assert (
        repository.resolve_snapshot(valid_id, nasr_product(), source_id="faa-aeronav", at=NOW).id
        == valid_id
    )


def test_revoke_requires_nonblank_reason_and_preserves_active_snapshot(tmp_path):
    repository = Repository(tmp_path / "data")
    asset = acquired(repository, airport_zip(tmp_path))
    snapshot_id = build_research_from_asset(repository, nasr_product(), asset.sha256, at=NOW)[
        "snapshot_id"
    ]
    repository.activate_snapshot(snapshot_id, nasr_product(), at=NOW)
    result = invoke(repository, "revoke-snapshot", "--snapshot-id", snapshot_id, "--reason", " ")
    assert result.exit_code == 1
    assert (
        repository.resolve_snapshot(snapshot_id, nasr_product(), source_id="faa-aeronav", at=NOW).id
        == snapshot_id
    )
