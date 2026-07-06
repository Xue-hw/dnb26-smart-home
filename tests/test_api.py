from fastapi.testclient import TestClient

from backend.app import create_app


def test_health() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_control_light() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/control",
        json={"target": "light", "action": "set", "value": 80},
    )
    assert response.status_code == 200
    assert response.json()["status"]["light_level"] == 80
