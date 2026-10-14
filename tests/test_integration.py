from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app import cache, db

client = TestClient(app)


def test_health_checks_real_services():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["postgres"] is True
    assert response.json()["redis"] is True


def test_tiers_are_loaded_from_postgres():
    response = client.get("/tiers")
    assert response.status_code == 200
    names = {item["name"] for item in response.json()["tiers"]}
    assert {"free", "basic", "pro"}.issubset(names)


def test_create_key_and_read_it_back():
    owner = f"integration-{uuid4().hex[:8]}"
    response = client.post(
        "/keys", json={"owner": owner, "tier": "free"}
    )
    assert response.status_code == 201
    api_key = response.json()["api_key"]

    try:
        result = client.get(f"/keys/{api_key}")
        assert result.status_code == 200
        assert result.json()["owner"] == owner
        assert result.json()["tier"] == "free"
    finally:
        db.query("DELETE FROM requests WHERE api_key=%s", (api_key,), fetch=False)
        db.query("DELETE FROM api_keys WHERE api_key=%s", (api_key,), fetch=False)
        cache.drop_prefix(f"rl:fixed:{api_key}")
        cache.drop(f"rl:slide:{api_key}")


def test_api_request_is_recorded():
    owner = f"integration-{uuid4().hex[:8]}"
    response = client.post(
        "/keys", json={"owner": owner, "tier": "free"}
    )
    assert response.status_code == 201
    api_key = response.json()["api_key"]

    try:
        result = client.get(
            "/api/echo",
            headers={"X-API-Key": api_key},
            params={"algorithm": "sliding"},
        )
        assert result.status_code == 200

        usage = client.get(f"/usage/{api_key}")
        assert usage.status_code == 200
        assert usage.json()["recent"][0]["status"] == 200
    finally:
        db.query("DELETE FROM requests WHERE api_key=%s", (api_key,), fetch=False)
        db.query("DELETE FROM api_keys WHERE api_key=%s", (api_key,), fetch=False)
        cache.drop_prefix(f"rl:fixed:{api_key}")
        cache.drop(f"rl:slide:{api_key}")


def test_invalid_api_key_is_rejected():
    response = client.get(
        "/api/echo",
        headers={"X-API-Key": "k_integration_missing"},
    )
    assert response.status_code == 404
