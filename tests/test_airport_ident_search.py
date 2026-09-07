"""Airport search uses explicit source identifiers; fixtures are synthetic only."""

from research_helpers import NOW, airport, candidate, product, report
from test_research_api import configured


def test_search_matches_explicit_icao_and_ranks_it_before_name_matches(tmp_path):
    client, repo, raw, _, _ = configured(tmp_path)
    explicit = airport(raw, "TEST")
    explicit.properties["icao_id"] = "KZZZ"
    name_match = airport(raw, "AAAA")
    name_match.name = "Synthetic KZZZ training field"
    release = candidate(raw, "explicit-icao")
    repo.stage(release, [name_match, explicit], report(2))
    repo.promote(release.id, product(), at=NOW)

    response = client.get("/api/v1/search", params={"q": "kzzz", "release_id": release.id})
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["items"]] == [explicit.id, name_match.id]
    assert response.json()["items"][0]["identifier"] == "TEST"
    assert response.json()["items"][0]["properties"]["icao_id"] == "KZZZ"


def test_search_does_not_invent_icao_or_treat_query_as_wildcard(tmp_path):
    client, repo, raw, _, _ = configured(tmp_path)
    explicit = airport(raw, "TEST")
    explicit.properties["icao_id"] = "KZZZ"
    missing = airport(raw, "NONE")
    release = candidate(raw, "literal-identifiers")
    repo.stage(release, [explicit, missing], report(2))
    repo.promote(release.id, product(), at=NOW)

    for query in ["KTEST", "KNONE", "K%", "K_ZZ"]:
        response = client.get("/api/v1/search", params={"q": query, "release_id": release.id})
        assert response.status_code == 200
        assert response.json()["items"] == []
