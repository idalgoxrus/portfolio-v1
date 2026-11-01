"""Smoke-тест HTTP-слоя: health endpoint.

Тест не требует токена бота и не делает сетевых вызовов: поднимает ASGI-приложение
напрямую через TestClient.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok() -> None:
    """GET /health отвечает 200 и {"status": "ok"} (с прогоном lifespan)."""
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_is_json_and_idempotent() -> None:
    """Эндпоинт отдаёт JSON и стабилен при повторных вызовах."""
    client = TestClient(app)

    first = client.get("/health")
    second = client.get("/health")

    assert first.headers["content-type"].startswith("application/json")
    assert first.json() == second.json() == {"status": "ok"}


def test_unknown_path_returns_404() -> None:
    """Неизвестный путь не маскируется под успех."""
    client = TestClient(app)

    assert client.get("/unknown").status_code == 404
