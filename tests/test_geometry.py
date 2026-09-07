"""Synthetic geometry fixtures, never evidence of FAA procedure coverage."""

import math
from itertools import pairwise

import pytest
from flightmap_ingestion.geometry import geometry_for_legs, nominal_geodesic
from flightmap_schema import Provenance, ResearchRecord
from geographiclib.geodesic import Geodesic


def leg(index, terminator, lon=0.0, lat=0.0, branch="main", resolution="unique"):
    return ResearchRecord(
        id=f"synthetic-leg-{index}",
        kind="leg",
        name=f"Synthetic {index}",
        parent_id="synthetic-procedure",
        branch_id=branch,
        sequence=index * 10,
        provenance=Provenance(asset_sha256="a" * 64, line=index + 1, locator="synthetic"),
        properties={
            "path_terminator": terminator,
            "fix_resolution": resolution,
            "resolved_fix": {"id": f"point-{index}", "longitude": lon, "latitude": lat},
        },
    )


def lines(geometry):
    return (
        geometry["coordinates"]
        if geometry["type"] == "MultiLineString"
        else [geometry["coordinates"]]
    )


def test_equator_golden_length_and_sampling():
    geometry = nominal_geodesic((0, 0), (1, 0))
    coordinates = geometry["coordinates"]
    assert coordinates[0] == pytest.approx([0, 0], abs=1e-12)
    assert coordinates[-1] == pytest.approx([1, 0], abs=1e-12)
    distances = [
        Geodesic.WGS84.Inverse(a[1], a[0], b[1], b[0])["s12"]
        for a, b in pairwise(coordinates)
    ]
    # Independent WGS84 equatorial analytic result: a * pi / 180.
    assert sum(distances) == pytest.approx(6378137 * math.pi / 180, abs=1e-6)
    assert max(distances) <= 1852 + 1e-6
    assert len(coordinates) == 62


@pytest.mark.parametrize("start,end", [((179, 25), (-179, 25)), ((-179, 25), (179, 25))])
def test_antimeridian_split_is_exact_and_reversible(start, end):
    geometry = nominal_geodesic(start, end)
    assert geometry["type"] == "MultiLineString"
    first, second = geometry["coordinates"]
    assert abs(first[-1][0]) == 180
    assert first[-1][0] == -second[0][0]
    assert first[-1][1] == second[0][1]
    assert first[0] == pytest.approx(start)
    assert second[-1] == pytest.approx(end)
    for segment in lines(geometry):
        for a, b in pairwise(segment):
            assert abs(a[0] - b[0]) <= 180
            assert Geodesic.WGS84.Inverse(a[1], a[0], b[1], b[0])["s12"] <= 1852 + 1e-6


@pytest.mark.parametrize(
    "start,end", [((180, 0), (179, 0)), ((-180, 0), (-179, 0)), ((179, 0), (180, 0))]
)
def test_boundary_endpoints_do_not_make_world_spanning_segments(start, end):
    for segment in lines(nominal_geodesic(start, end)):
        assert all(abs(a[0] - b[0]) <= 180 for a, b in pairwise(segment))


def test_unknown_leg_and_failed_tf_break_the_chain_until_an_if():
    result = geometry_for_legs(
        [leg(0, "IF"), leg(1, "TF", 1), leg(2, "RF", 2), leg(3, "TF", 3),
         leg(4, "TF", 4), leg(5, "IF", 5), leg(6, "TF", 6)]
    )
    assert [item["id"] for item in result["features"]] == [
        "synthetic-leg-0", "synthetic-leg-1", "synthetic-leg-5", "synthetic-leg-6"
    ]
    assert [gap["reason"] for gap in result["gaps"]] == [
        "unsupported-path-terminator", "previous-leg-not-supported", "previous-leg-not-supported"
    ]


def test_selected_branch_does_not_skip_an_intervening_original_leg():
    result = geometry_for_legs(
        [leg(0, "IF"), leg(1, "IF", 1, branch="missed"), leg(2, "TF", 2)], "main"
    )
    assert len(result["features"]) == 1
    assert result["gaps"][0]["reason"] == "branch-boundary"


@pytest.mark.parametrize("resolution", ["missing", "ambiguous", "unverified", ""])
def test_only_explicit_unique_reference_can_draw(resolution):
    result = geometry_for_legs([leg(0, "IF", resolution=resolution), leg(1, "TF", 1)])
    assert not result["features"]
    assert len(result["gaps"]) == 2


@pytest.mark.parametrize("lon,lat", [(181, 0), (0, 91), (float("nan"), 0), (0, True)])
def test_invalid_coordinate_breaks_chain(lon, lat):
    result = geometry_for_legs([leg(0, "IF", lon, lat), leg(1, "TF", 1)])
    assert not result["features"]


def test_sequence_order_is_not_silently_sorted():
    result = geometry_for_legs([leg(2, "IF"), leg(1, "TF", 1)])
    assert result["gaps"][0]["reason"] == "invalid-original-order"


def test_procedures_with_identical_branch_names_never_connect():
    other = leg(1, "TF", 1).model_copy(update={"parent_id": "another-procedure"})
    result = geometry_for_legs([leg(0, "IF"), other])
    assert result["gaps"][0]["reason"] == "branch-boundary"


def test_coincident_points_remain_valid_geojson():
    result = nominal_geodesic((1, 2), (1, 2))
    assert result == {"type": "LineString", "coordinates": [[1, 2], [1, 2]]}


@pytest.mark.parametrize("provenance_change", [{"asset_sha256": "b" * 64}, {"member": "other"}])
def test_separate_source_members_cannot_be_joined(provenance_change):
    second = leg(1, "TF", 1)
    second.provenance = second.provenance.model_copy(update=provenance_change)
    result = geometry_for_legs([leg(0, "IF"), second])
    assert result["gaps"][0]["reason"] == "source-boundary"


@pytest.mark.parametrize("source_line", [None, 1])
def test_missing_or_reversed_source_order_cannot_authorize_a_tf(source_line):
    second = leg(1, "TF", 1)
    second.provenance = second.provenance.model_copy(update={"line": source_line})
    result = geometry_for_legs([leg(0, "IF"), second])
    assert result["gaps"][0]["reason"] == "source-order-unverified"
