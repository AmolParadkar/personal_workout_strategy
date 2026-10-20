from fastapi.testclient import TestClient

from api.main import app
from core import __version__

client = TestClient(app)


def test_health_returns_ok_and_version():
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
