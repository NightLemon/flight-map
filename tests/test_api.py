import pytest
from fastapi.testclient import TestClient
from flightmap_api.main import create_app


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(data_dir=tmp_path / "empty-api"))


def test_health(client) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_status_does_not_claim_unverified_data(client) -> None:
    response = client.get("/api/v1/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["verified_release_available"] is False
    assert payload["publication_state"] == "empty"
    assert "不得用于" in payload["disclaimer"]


def test_coverage_is_explicitly_not_imported(client) -> None:
    response = client.get("/api/v1/coverage")

    assert response.status_code == 200
    assert response.json()
    assert all(item["status"] == "not-imported" for item in response.json())
