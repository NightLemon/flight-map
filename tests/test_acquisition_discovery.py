from flightmap_ingestion.faa import FaaDiscovery
from flightmap_schema import load_sources


def product(identifier):
    return next(p for s in load_sources("sources/us/faa.yml") for p in s.products if p.id == identifier)


def test_nasr_pages_assets_and_tests_are_distinct():
    html = '''<a href="2026-09-03">Current</a>
    <a href="https://nfdc.faa.gov/extra/03_Sep_2026_APT_CSV.zip">Airports</a>
    <a href="https://nfdc.faa.gov/extra/03_Sep_2026_APT_CSV_TEST.zip">Test</a>
    <a href="https://example.org/03_Sep_2026_APT_CSV.zip">Other</a>'''
    candidates = FaaDiscovery().discover_html(product("nasr"), html)
    assert [(c.kind, c.role) for c in candidates] == [
        ("product-page", "edition"), ("asset", "airport-csv")
    ]


def test_ifr_does_not_match_certification_navigation():
    html = '<a href="/certification/">Certification</a><a href="chart.tif">GeoTIFF</a>'
    candidates = FaaDiscovery().discover_html(product("ifr-charts"), html)
    assert len(candidates) == 1
    assert candidates[0].url.endswith("chart.tif")


def test_cifp_agreement_is_not_an_asset():
    candidates = FaaDiscovery().discover_html(
        product("cifp"), '<a href="download/">I agree</a><a href="javascript:void">Download CIFP</a>'
    )
    assert len(candidates) == 1
    assert candidates[0].kind == "agreement"


def test_dtpp_xml_is_separate_from_large_chart_package():
    html = '''<a href="https://aeronav.faa.gov/d-tpp/2609/xml_data/d-tpp_Metafile.xml">Catalog</a>
    <a href="https://aeronav.faa.gov/upload_313-d/terminal/DDTPPA_260903.zip">PDF ZIP</a>'''
    candidates = FaaDiscovery().discover_html(product("dtpp"), html)
    assert [c.role for c in candidates] == ["chart-catalog", "chart-package"]
