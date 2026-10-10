from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError

from app.main import create_app


def test_database_errors_become_a_generic_503() -> None:
    test_app = create_app()

    @test_app.get("/boom")
    async def boom() -> None:
        raise ServerSelectionTimeoutError("user:secret-password@internal-host:27017 timed out")

    response = TestClient(test_app).get("/boom")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database temporarily unavailable."}
    assert "secret-password" not in response.text
    assert "internal-host" not in response.text
