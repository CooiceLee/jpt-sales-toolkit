#!/usr/bin/env python3
"""Offline regression tests for provider-neutral geocoding."""

from __future__ import annotations

import tempfile
import ssl
import urllib.error
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.routers.deps import get_current_user
from backend.routers.intake import (
    GeocodeRequest, geocode_address, get_geocode_service, router as intake_router,
    search_addresses,
)
from backend.services.geocode_service import GeocodeService
from backend.services.geocoding import AmapProvider, GeocodingCoordinator, GeocodingError
from backend.services.geocoding.cache import GeocodeCache
from backend.services.geocoding.coordinates import gcj02_to_wgs84
from backend.services.geocoding.models import GeocodeQuery
from backend.services.geocoding.nominatim import NominatimProvider
from backend.services.geocoding.rate_limit import SharedRateLimiter
from backend.services.geocoding.transport import JsonTransport


PARIS_RESULT = [{
    "place_id": 1001,
    "lat": "48.8737917",
    "lon": "2.2950275",
    "display_name": "Arc de Triomphe, Place Charles de Gaulle, 75008 Paris, France",
    "type": "monument",
    "importance": 0.72,
}]


class NoopLimiter:
    def wait(self) -> None:
        pass


class FakeTransport:
    def __init__(self, payload) -> None:
        self.payload = payload
        self.calls = []

    def get(self, url, params, headers, provider):
        self.calls.append({"url": url, "params": params, "provider": provider})
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def coordinator(path: Path, payload=PARIS_RESULT):
    transport = FakeTransport(payload)
    provider = NominatimProvider("JPT-Test", transport=transport, limiter=NoopLimiter())
    return GeocodingCoordinator([provider, AmapProvider(None)], GeocodeCache(path)), transport


def fallback_coordinator(path: Path, amap_payload, global_payload=PARIS_RESULT):
    amap_transport = FakeTransport(amap_payload)
    global_transport = FakeTransport(global_payload)
    amap = AmapProvider("local-test-key", transport=amap_transport, limiter=NoopLimiter())
    global_provider = NominatimProvider(
        "JPT-Test", transport=global_transport, limiter=NoopLimiter()
    )
    return (
        GeocodingCoordinator([amap, global_provider], GeocodeCache(path)),
        amap_transport,
        global_transport,
    )


def test_europe_address_postcode_candidates_and_cache() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt_geocode_") as temp_dir:
        service_coordinator, transport = coordinator(Path(temp_dir) / "cache.sqlite3")
        query = GeocodeQuery.create(
            address="Arc de Triomphe", city="Paris", postal_code="75008", country="France"
        )
        first = service_coordinator.search(query, limit=5)
        second = service_coordinator.search(
            GeocodeQuery.create(
                address="  arc   DE triomphe ", city="PARIS",
                postal_code="75008", country="france",
            ),
            limit=1,
        )
    assert len(first.candidates) == 1
    assert first.candidates[0].lat == 48.8737917
    assert first.candidates[0].provider == "nominatim"
    assert first.candidates[0].confidence == "low"
    assert "75008" in transport.calls[0]["params"]["q"]
    assert len(transport.calls) == 1, "equivalent normalized query should use the sidecar cache"
    assert second.cached is True


def test_prominence_never_implies_exact_address_precision() -> None:
    provider = NominatimProvider(
        "JPT-Test",
        transport=FakeTransport(PARIS_RESULT),
        limiter=NoopLimiter(),
    )
    prominent_landmark = provider.search(GeocodeQuery.create(city="Paris"), 1)[0]
    assert prominent_landmark.confidence == "low"

    provider.transport = FakeTransport([{
        **PARIS_RESULT[0],
        "type": "house",
        "importance": 0.05,
    }])
    precise_house = provider.search(GeocodeQuery.create(address="10 Rue Test"), 1)[0]
    assert precise_house.confidence == "high"


def test_no_result_is_distinct_from_provider_failure() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt_geocode_") as temp_dir:
        empty_coordinator, empty_transport = coordinator(Path(temp_dir) / "empty.sqlite3", [])
        empty_query = GeocodeQuery.create(postal_code="00000", country="France")
        assert empty_coordinator.search(empty_query, limit=5).candidates == []
        assert empty_coordinator.search(empty_query, limit=5).cached is True
        assert len(empty_transport.calls) == 1, "no-result responses need a short negative cache"
        empty_service = GeocodeService(empty_coordinator)
        search = search_addresses(
            GeocodeRequest(postal_code="00000", country="France"),
            user={"id": "leader", "role": "leader"},
            service=empty_service,
        )
        assert search["candidates"] == []
        try:
            geocode_address(
                GeocodeRequest(postal_code="00000", country="France"),
                user={"id": "leader", "role": "leader"},
                service=empty_service,
            )
        except HTTPException as exc:
            assert exc.status_code == 404
            assert exc.detail == "Address not found"
        else:
            raise AssertionError("legacy endpoint should preserve 404 for a genuine no-result")
        assert len(empty_transport.calls) == 1

        failure = GeocodingError(
            "network_error", "Map service could not be reached.", provider="nominatim"
        )
        failed_coordinator, _ = coordinator(Path(temp_dir) / "failed.sqlite3", failure)
        try:
            search_addresses(
                GeocodeRequest(city="Paris"),
                user={"id": "leader", "role": "leader"},
                service=GeocodeService(failed_coordinator),
            )
        except HTTPException as exc:
            assert exc.status_code == 503
            assert exc.detail["code"] == "network_error"
            assert exc.detail["retryable"] is True
        else:
            raise AssertionError("provider failure must not be reported as address-not-found")


def test_optional_amap_is_safe_without_key() -> None:
    provider = AmapProvider(None)
    assert provider.enabled is False
    try:
        provider.search(GeocodeQuery.create(city="Shanghai", country="China"), 1)
    except GeocodingError as exc:
        assert exc.code == "provider_disabled"
        assert exc.retryable is False
    else:
        raise AssertionError("unconfigured Amap provider must remain disabled")


def test_amap_coordinates_are_normalized_to_wgs84() -> None:
    transport = FakeTransport({
        "status": "1",
        "geocodes": [{
            "formatted_address": "上海市黄浦区人民大道200号",
            "location": "121.473700,31.230400",
            "level": "门牌号",
        }],
    })
    provider = AmapProvider("local-test-key", transport=transport, limiter=NoopLimiter())
    candidate = provider.search(GeocodeQuery.create(city="上海", country="中国"), 1)[0]
    assert candidate.provider == "amap"
    assert (candidate.lat, candidate.lng) != (31.2304, 121.4737)
    assert abs(candidate.lat - 31.2304) < 0.02
    assert abs(candidate.lng - 121.4737) < 0.02
    assert "local-test-key" not in repr(candidate)
    direct = gcj02_to_wgs84(31.2304, 121.4737)
    assert direct == (candidate.lat, candidate.lng)


def test_amap_retryable_failures_and_empty_results_fall_back() -> None:
    cases = {
        "empty": {"status": "1", "geocodes": []},
        "quota": {"status": "0", "infocode": "10003"},
        "network": GeocodingError(
            "network_error", "Map service could not be reached.", provider="amap"
        ),
        "malformed": {"status": "1", "geocodes": [{"location": "invalid"}]},
    }
    with tempfile.TemporaryDirectory(prefix="jpt_geocode_fallback_") as temp_dir:
        for name, payload in cases.items():
            service_coordinator, amap_transport, global_transport = fallback_coordinator(
                Path(temp_dir) / f"{name}.sqlite3", payload
            )
            query = GeocodeQuery.create(
                address="Arc de Triomphe", city="Paris", country="France"
            )
            first = service_coordinator.search(query, limit=1)
            second = service_coordinator.search(query, limit=1)
            assert first.provider == "nominatim", name
            assert len(first.candidates) == 1, name
            assert second.provider == "nominatim", name
            assert len(global_transport.calls) == 1, name
            if name == "empty":
                assert len(amap_transport.calls) == 1, "empty Amap results need negative caching"
            else:
                assert len(amap_transport.calls) == 2, "provider failures must not be cached"


def test_amap_failures_are_typed_and_auth_does_not_fall_back() -> None:
    malformed = AmapProvider(
        "local-test-key",
        transport=FakeTransport({"status": "1", "geocodes": [{"location": "invalid"}]}),
        limiter=NoopLimiter(),
    )
    try:
        malformed.search(GeocodeQuery.create(city="Paris"), 1)
    except GeocodingError as exc:
        assert exc.code == "invalid_response"
        assert exc.status_code == 502
        assert exc.provider == "amap"
    else:
        raise AssertionError("malformed Amap coordinates must raise a typed error")

    quota = AmapProvider(
        "local-test-key",
        transport=FakeTransport({"status": "0", "infocode": "10014"}),
        limiter=NoopLimiter(),
    )
    try:
        quota.search(GeocodeQuery.create(city="Paris"), 1)
    except GeocodingError as exc:
        assert exc.code == "provider_quota"
        assert exc.status_code == 429
        assert exc.retryable is True
    else:
        raise AssertionError("Amap quota errors must remain typed")

    with tempfile.TemporaryDirectory(prefix="jpt_geocode_auth_") as temp_dir:
        service_coordinator, _, global_transport = fallback_coordinator(
            Path(temp_dir) / "auth.sqlite3",
            {"status": "0", "infocode": "10001"},
        )
        try:
            service_coordinator.search(GeocodeQuery.create(city="Paris"), limit=1)
        except GeocodingError as exc:
            assert exc.code == "provider_auth"
            assert exc.retryable is False
        else:
            raise AssertionError("configuration/auth failures must not be hidden by fallback")
        assert global_transport.calls == []


def test_shared_rate_limit() -> None:
    now = [10.0]
    delays = []

    def sleep(delay: float) -> None:
        delays.append(delay)
        now[0] += delay

    limiter = SharedRateLimiter(1.0, clock=lambda: now[0], sleeper=sleep)
    limiter.wait()
    now[0] += 0.25
    limiter.wait()
    assert delays == [0.75]


def test_transport_error_classification() -> None:
    transport = JsonTransport()
    cases = [
        (ssl.SSLCertVerificationError(1, "certificate verify failed"), "tls_error", 503),
        (urllib.error.HTTPError("https://example", 403, "Forbidden", {}, None), "provider_auth", 502),
        (urllib.error.HTTPError("https://example", 429, "Too Many", {}, None), "provider_quota", 429),
    ]
    for failure, code, status_code in cases:
        with patch("backend.services.geocoding.transport.urllib.request.urlopen", side_effect=failure):
            try:
                transport.get("https://example", {}, {}, "test")
            except GeocodingError as exc:
                assert exc.code == code
                assert exc.status_code == status_code
                assert exc.provider == "test"
            else:
                raise AssertionError(f"{code} failure was not classified")


def test_legacy_endpoint_returns_flat_first_candidate() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt_geocode_") as temp_dir:
        service_coordinator, _ = coordinator(Path(temp_dir) / "legacy.sqlite3")
        result = geocode_address(
            GeocodeRequest(
                address="Arc de Triomphe", city="Paris", postal_code="75008", country="France"
            ),
            user={"id": "leader", "role": "leader"},
            service=GeocodeService(service_coordinator),
        )
    assert result["lat"] == 48.8737917
    assert "candidates" not in result
    assert result["normalized_address"].startswith("Arc de Triomphe")


def test_http_routes_preserve_new_and_legacy_contracts() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt_geocode_") as temp_dir:
        service_coordinator, _ = coordinator(Path(temp_dir) / "routes.sqlite3")
        app = FastAPI()
        app.include_router(intake_router, prefix="/api")
        app.dependency_overrides[get_current_user] = lambda: {
            "id": "leader", "role": "leader"
        }
        app.dependency_overrides[get_geocode_service] = lambda: GeocodeService(service_coordinator)
        with TestClient(app) as client:
            payload = {
                "address": "Arc de Triomphe", "city": "Paris",
                "postal_code": "75008", "country": "France",
            }
            candidate_response = client.post("/api/intake/geocode/search", json=payload)
            legacy_response = client.post("/api/intake/geocode", json=payload)
    assert candidate_response.status_code == 200, candidate_response.text
    assert len(candidate_response.json()["candidates"]) == 1
    assert legacy_response.status_code == 200, legacy_response.text
    assert legacy_response.json()["lat"] == 48.8737917
    assert "candidates" not in legacy_response.json()


def test_frozen_certificate_asset_contract() -> None:
    spec = Path("packaging/jpt_sales_toolkit.spec").read_text(encoding="utf-8")
    transport = Path("backend/services/geocoding/transport.py").read_text(encoding="utf-8")
    assert 'collect_data_files("certifi")' in spec
    assert "ssl.create_default_context(cafile=certifi.where())" in transport


def main() -> None:
    for test in (
        test_europe_address_postcode_candidates_and_cache,
        test_prominence_never_implies_exact_address_precision,
        test_no_result_is_distinct_from_provider_failure,
        test_optional_amap_is_safe_without_key,
        test_amap_coordinates_are_normalized_to_wgs84,
        test_amap_retryable_failures_and_empty_results_fall_back,
        test_amap_failures_are_typed_and_auth_does_not_fall_back,
        test_shared_rate_limit,
        test_transport_error_classification,
        test_legacy_endpoint_returns_flat_first_candidate,
        test_http_routes_preserve_new_and_legacy_contracts,
        test_frozen_certificate_asset_contract,
    ):
        test()
        print(f"PASS: {test.__name__}")
    print("PASS: geocoding service regression completed")


if __name__ == "__main__":
    main()
