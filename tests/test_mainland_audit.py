"""Focused contract tests for the offline mainland reference audit."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "audit_mainland_reference", Path("scripts/audit_mainland_reference.py")
)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def frequency_record(frequency: str = "122.8") -> dict:
    return {
        "id": "ourairports:communication:5",
        "kind": "communication",
        "airport_id": "ourairports:airport:1",
        "parent_id": "ourairports:airport:1",
        "properties": {
            "service": "CTAF",
            "frequency": frequency,
            "unit": "MHz",
            "remarks": "Common traffic",
        },
        "provenance": {
            "member": "airport-frequencies.csv",
            "line": 2,
            "asset_sha256": "input-sha",
        },
    }


def write_frequency_detail(export_dir: Path, collections: dict[str, list[dict]]) -> None:
    directory = export_dir / "airports"
    directory.mkdir(parents=True)
    (directory / "1.json").write_text(
        json.dumps({"ourairports:airport:1": collections}), encoding="utf-8"
    )


def test_export_contract_recognizes_legacy_and_reviewed_shapes() -> None:
    assert not audit.is_reviewed_export({"counts": {"communications": 1}})
    assert audit.is_reviewed_export(
        {
            "counts": {
                "communications": 1,
                "navigation_frequencies": 0,
                "unclassified_frequencies": 0,
            }
        }
    )


def test_strict_mode_rejects_a_legacy_manifest_before_reading_inputs(tmp_path: Path) -> None:
    reference = tmp_path / "pages-public" / "reference"
    dataset_revision = "0" * 40
    (reference / dataset_revision).mkdir(parents=True)
    (reference / "manifest.json").write_text(
        json.dumps(
            {
                "source": {"revision": audit.REVISION},
                "dataset_revision": dataset_revision,
                "counts": {"communications": 1},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="rejects the legacy export contract"):
        audit.audit(tmp_path, require_reviewed=True)


@pytest.mark.parametrize(
    ("collections", "match"),
    [
        (
            {
                "communications": [],
                "navigation_frequencies": [],
                "unclassified_frequencies": [],
            },
            "detail/source id mismatch",
        ),
        (
            {
                "communications": [frequency_record()],
                "navigation_frequencies": [frequency_record()],
                "unclassified_frequencies": [],
            },
            "multiple detail categories",
        ),
        (
            {
                "communications": [frequency_record("123.4")],
                "navigation_frequencies": [],
                "unclassified_frequencies": [],
            },
            "provenance/value mismatch",
        ),
    ],
)
def test_frequency_detail_audit_rejects_missing_duplicate_and_changed_values(
    tmp_path: Path, collections: dict[str, list[dict]], match: str
) -> None:
    export_dir = tmp_path / "export"
    write_frequency_detail(export_dir, collections)
    mainland = [(2, {"id": "1"})]
    source_rows = [
        (
            2,
            {
                "id": "5",
                "airport_ref": "1",
                "type": "CTAF",
                "frequency_mhz": "122.8",
                "description": "Common traffic",
            },
        )
    ]
    with pytest.raises(ValueError, match=match):
        audit.reviewed_frequency_export(export_dir, mainland, source_rows, {"1"}, "input-sha")


def review_manifest(review_sha256: str, note_count: int = 0) -> dict:
    return {
        "review": {
            "reviewed_at": "2026-09-08",
            "source_revision": audit.REVISION,
            "sha256": review_sha256,
            "correction_count": 1,
            "note_count": note_count,
        }
    }


def write_review(export_dir: Path, notes: list[dict] | None = None) -> tuple[Path, str]:
    document = {
        "schema": 1,
        "source_revision": audit.REVISION,
        "reviewed_at": "2026-09-08",
        "corrections": [
            {
                "airport_id": "ourairports:airport:525151",
                "record_id": "ourairports:airport:525151",
                "field": "name",
                "original_value": "Bozhou Airport (under construction)",
                "value": "Bozhou Airport",
                "evidence": [{"url": "https://example.invalid/evidence"}],
            }
        ],
        "notes": notes or [],
    }
    path = export_dir / "review.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def bozhou_details(original_name: str = "Bozhou Airport (under construction)") -> dict:
    return {
        "ourairports:airport:525151": {
            "airport": {"name": "Bozhou Airport", "properties": {"original_name": original_name}},
            "communications": [],
            "navigation_frequencies": [],
            "unclassified_frequencies": [],
            "runways": [],
            "review_notes": [],
        }
    }


def expected_detail_notes(review_path: Path) -> list[dict]:
    catalog = json.loads(review_path.read_text(encoding="utf-8"))
    return [
        {**entry, "reviewed_at": catalog["reviewed_at"]}
        for entry in [*catalog["corrections"], *catalog["notes"]]
    ]


def test_review_gate_rejects_closed_map_feature_and_review_provenance_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    export_dir = tmp_path / "export"
    review_path, digest = write_review(export_dir)
    monkeypatch.setattr(audit, "REVIEW_CATALOG", review_path)
    details = bozhou_details()
    details["ourairports:airport:525151"]["review_notes"] = expected_detail_notes(review_path)
    closed_runway = (2, {"id": "7", "airport_ref": "525151", "closed": "0"})
    airports = {
        "525151": (2, {"type": "closed", "name": "Bozhou Airport (under construction)"})
    }

    with pytest.raises(ValueError, match="closed-airport runway"):
        audit.require_reviewed_acceptance(
            review_manifest(digest),
            export_dir,
            details,
            Counter({"ourairports:runway:7": 1}),
            [closed_runway],
            airports,
            set(),
        )


def test_review_gate_rejects_tampered_or_missing_detail_notes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog_note = {
        "id": "bozhou-service-note",
        "airport_id": "ourairports:airport:525151",
        "record_id": "ourairports:airport:525151",
        "field": "properties.scheduled_service",
        "original_value": "no",
        "status": "needs_review",
        "message": "Preserve source value.",
        "evidence": [{"url": "https://example.invalid/note"}],
    }
    export_dir = tmp_path / "export"
    review_path, digest = write_review(export_dir, [catalog_note])
    monkeypatch.setattr(audit, "REVIEW_CATALOG", review_path)
    details = bozhou_details()
    details["ourairports:airport:525151"]["airport"]["properties"]["scheduled_service"] = "no"
    details["ourairports:airport:525151"]["review_notes"] = [
        {
            **catalog_note,
            "reviewed_at": "2026-09-08",
            "message": "Tampered",
        }
    ]
    airports = {
        "525151": (2, {"type": "closed", "name": "Bozhou Airport (under construction)"})
    }
    with pytest.raises(ValueError, match="review_notes do not exactly match"):
        audit.require_reviewed_acceptance(
            review_manifest(digest, note_count=1),
            export_dir,
            details,
            Counter(),
            [],
            airports,
            set(),
        )
    details["ourairports:airport:525151"]["review_notes"] = []
    with pytest.raises(ValueError, match="review_notes do not exactly match"):
        audit.require_reviewed_acceptance(
            review_manifest(digest, note_count=1),
            export_dir,
            details,
            Counter(),
            [],
            airports,
            set(),
        )
    expected = expected_detail_notes(review_path)
    original_name_details = bozhou_details("Different source name")
    original_name_details["ourairports:airport:525151"]["review_notes"] = expected
    with pytest.raises(ValueError, match="original_name provenance"):
        audit.require_reviewed_acceptance(
            review_manifest(digest, note_count=1),
            export_dir,
            original_name_details,
            Counter(),
            [],
            airports,
            set(),
        )
    with pytest.raises(ValueError, match="SHA-256"):
        audit.require_reviewed_acceptance(
            review_manifest("0" * 64, note_count=1),
            export_dir,
            details,
            Counter(),
            [],
            airports,
            set(),
        )
