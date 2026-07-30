#!/usr/bin/env python3
"""Structural and permission contracts for the split intake router."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers import intake, intake_geocoding
from backend.routers.deps import get_current_user


ROOT = Path(__file__).parent


class FakeGeocodeService:
    def __init__(self) -> None:
        self.calls = 0

    def search(self, **values):
        self.calls += 1
        return {"query": values, "candidates": [], "provider": "test", "cached": False}


def test_module_boundary_and_re_exports() -> None:
    assert len((ROOT / "backend/routers/intake.py").read_text().splitlines()) <= 125
    assert len((ROOT / "backend/routers/intake_geocoding.py").read_text().splitlines()) <= 125
    for name in (
        "GeocodeRequest", "get_geocode_service", "_geocoding_http_error",
        "search_addresses", "geocode_address",
    ):
        assert getattr(intake, name) is getattr(intake_geocoding, name)
    paths = [route.path for route in intake.router.routes]
    assert paths.count("/intake/geocode/search") == 1
    assert paths.count("/intake/geocode") == 1


def test_child_routes_keep_parent_role_boundary() -> None:
    service = FakeGeocodeService()
    app = FastAPI()
    app.include_router(intake.router, prefix="/api")
    app.dependency_overrides[intake.get_geocode_service] = lambda: service

    app.dependency_overrides[get_current_user] = lambda: {"id": "tech", "role": "tech"}
    with TestClient(app) as client:
        denied = client.post("/api/intake/geocode/search", json={"city": "Paris"})
    assert denied.status_code == 403
    assert service.calls == 0

    app.dependency_overrides[get_current_user] = lambda: {"id": "sales", "role": "sales"}
    with TestClient(app) as client:
        allowed = client.post("/api/intake/geocode/search", json={"city": "Paris"})
    assert allowed.status_code == 200
    assert service.calls == 1


def main() -> None:
    test_module_boundary_and_re_exports()
    test_child_routes_keep_parent_role_boundary()
    print("PASS: split intake router keeps imports, paths and Leader/Sales boundary")


if __name__ == "__main__":
    main()
