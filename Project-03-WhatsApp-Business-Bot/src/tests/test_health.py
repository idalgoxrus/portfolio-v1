"""Tests for the /health endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_content_type_is_json() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.headers["content-type"].startswith("application/json")


def test_docs_endpoint_available() -> None:
    with TestClient(app) as client:
        response = client.get("/docs")

    assert response.status_code == 200
