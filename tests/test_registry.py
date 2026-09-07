from pathlib import Path

from flightmap_schema import LicenseStatus, load_sources

ROOT = Path(__file__).parents[1]


def test_faa_registry_is_valid_and_fail_closed() -> None:
    sources = load_sources(ROOT / "sources/us/faa.yml")

    assert len(sources) == 1
    products = {product.id: product for product in sources[0].products}
    assert {"cifp", "nasr", "dtpp", "ifr-charts", "safety-alerts"} <= products.keys()
    assert all(
        product.license_status in {LicenseStatus.REVIEW_REQUIRED, LicenseStatus.LINK_ONLY}
        for product in products.values()
    )
    assert not any(product.license_status.allows_redistribution for product in products.values())
