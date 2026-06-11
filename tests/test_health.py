from fastapi.testclient import TestClient

from service_api import app


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["project_name"]
    assert payload["project_subtitle"]
