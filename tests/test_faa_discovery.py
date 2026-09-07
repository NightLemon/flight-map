from flightmap_ingestion.faa import FaaDiscovery
from flightmap_schema import LicenseStatus, SourceProduct


def test_discovery_only_reports_matching_links_without_inventing_validity() -> None:
    product = SourceProduct.model_validate(
        {
            "id": "cifp",
            "name": "CIFP",
            "landing_page": "https://www.faa.gov/products/cifp/",
            "kind": "structured-data",
            "categories": ["airways"],
            "license_status": LicenseStatus.REVIEW_REQUIRED,
            "redistribution": "not reviewed",
            "discovery": {"link_contains": ["cifp", "zip"], "require_zip": True},
        }
    )
    html = """
        <a href="/downloads/CIFP_260903.zip">Current CIFP 260903</a>
        <a href="/downloads/CIFP_260903.zip">Duplicate</a>
        <a href="manual.pdf">Unrelated manual</a>
    """

    candidates = FaaDiscovery().discover_html(product, html)

    assert len(candidates) == 1
    assert candidates[0].url == "https://www.faa.gov/downloads/CIFP_260903.zip"
    assert candidates[0].observed_date_token == "260903"
    assert not hasattr(candidates[0], "valid_from")
