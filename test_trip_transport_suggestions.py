"""Batch 3 transport suggestion safety and deterministic fallback tests."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from backend.services.trip_transport_suggestions import (
    LegRequest,
    OsrmDemoDriveProvider,
    TransportSuggestionService,
)
from backend.services.trip_transport_suggestions.links import validate_https_url, validate_osrm_url
from backend.services.trip_transport_suggestions.network import TransportProviderError


NOW = "2026-08-21T03:00:00Z"


class FakeLimiter:
    def __init__(self):
        self.calls = 0

    def wait(self):
        self.calls += 1


class FakeOsrmTransport:
    def __init__(self, payload=None, error=False):
        self.payload = payload or {"routes": [{"distance": 585_200, "duration": 21_240}]}
        self.error = error
        self.calls = []

    def get_osrm(self, url, user_agent):
        self.calls.append((url, user_agent))
        if self.error:
            raise TransportProviderError("synthetic failure")
        return self.payload


def request(mode="drive"):
    return LegRequest.create(
        leg_key="stop:berlin>stop:munich", mode=mode,
        from_lat=52.52, from_lng=13.405, to_lat=48.1351, to_lng=11.582,
    )


def check_default_is_local_and_user_confirmed():
    timestamps = iter((NOW, "2026-08-21T03:01:00Z"))
    service = TransportSuggestionService(now=lambda: next(timestamps))
    first = service.suggest(request()).as_dict()
    second = service.suggest(request()).as_dict()
    assert first["provider"] == "Local estimate" and first["online"] is False
    assert first["approximate"] is True and first["requires_manual_confirmation"] is True
    assert first["distance_km"] == second["distance_km"]
    assert first["time_hours"] == second["time_hours"]
    assert first["suggestion_id"] == second["suggestion_id"]
    assert first["cached"] is False and second["cached"] is True
    refreshed = service.suggest(request(), force_refresh=True).as_dict()
    assert refreshed["cached"] is False
    assert refreshed["fetched_at"] == "2026-08-21T03:01:00Z"


def check_links_are_coordinate_only_and_allowlisted():
    for mode, expected_mode in (("drive", "driving"), ("ground_public", "transit")):
        url = TransportSuggestionService(now=lambda: NOW).suggest(request(mode)).search_url
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        assert (parsed.scheme, parsed.hostname, parsed.path) == ("https", "www.google.com", "/maps/dir/")
        assert query["travelmode"] == [expected_mode]
        assert set(query) == {"api", "origin", "destination", "travelmode"}
        assert all("Berlin" not in value and "Munich" not in value for values in query.values() for value in values)
    flight = TransportSuggestionService(now=lambda: NOW).suggest(request("flight"))
    assert flight.search_url == "https://www.google.com/travel/flights"


def check_input_and_url_fail_closed():
    for values in (
        {"leg_key": '<img src=x onerror="alert(1)">', "mode": "drive"},
        {"leg_key": "a>b", "mode": "hovercraft"},
    ):
        try:
            LegRequest.create(**values, from_lat=0, from_lng=0, to_lat=1, to_lng=1)
            raise AssertionError("unsafe request accepted")
        except ValueError:
            pass
    unsafe = (
        "http://www.google.com/maps/dir/",
        "https://evil.example/maps/dir/",
        "https://www.google.com:443/maps/dir/",
        "https://user@www.google.com/maps/dir/",
        "https://www.google.com/maps/dir/#payload",
    )
    for url in unsafe:
        try:
            validate_https_url(url, {("www.google.com", "/maps/dir/")})
            raise AssertionError(f"unsafe URL accepted: {url}")
        except ValueError:
            pass
    for url in (
        "http://routing.openstreetmap.de/routed-car/route/v1/driving/1.000000,1.000000;2.000000,2.000000?overview=false&steps=false",
        "https://routing.openstreetmap.de/routed-car/route/v1/driving/../../admin?overview=false&steps=false",
        "https://routing.openstreetmap.de/routed-car/route/v1/driving/1.000000,1.000000;2.000000,2.000000?overview=false&steps=true",
        "https://routing.openstreetmap.de/routed-car/route/v1/driving/1.000000,1.000000;2.000000,2.000000?overview=false&steps=false#x",
    ):
        try:
            validate_osrm_url(url)
            raise AssertionError(f"unsafe OSRM URL accepted: {url}")
        except ValueError:
            pass


def check_optional_osrm_is_disabled_and_falls_back():
    transport, limiter = FakeOsrmTransport(), FakeLimiter()
    disabled = OsrmDemoDriveProvider(transport=transport, limiter=limiter)
    result = TransportSuggestionService(drive_provider=disabled, now=lambda: NOW).suggest(request())
    assert result.provider == "Local estimate" and transport.calls == [] and limiter.calls == 0

    failing_transport = FakeOsrmTransport(error=True)
    enabled = OsrmDemoDriveProvider(enabled=True, transport=failing_transport, limiter=limiter)
    fallback = TransportSuggestionService(drive_provider=enabled, now=lambda: NOW).suggest(request())
    assert fallback.provider == "Local estimate" and fallback.online is False
    assert len(failing_transport.calls) == 1


def check_optional_osrm_contract_and_response_sanitization():
    payload = {"routes": [{"distance": 585_200, "duration": 21_240, "name": "<script>x</script>"}]}
    transport, limiter = FakeOsrmTransport(payload), FakeLimiter()
    provider = OsrmDemoDriveProvider(enabled=True, transport=transport, limiter=limiter)
    result = TransportSuggestionService(drive_provider=provider, now=lambda: NOW).suggest(request()).as_dict()
    assert result["provider"] == "FOSSGIS OSRM demo" and result["online"] is True
    assert result["status"] == "estimated"
    assert result["distance_km"] == 585.2 and result["time_hours"] == 5.9
    assert "script" not in str(result).lower()
    assert limiter.calls == 1 and len(transport.calls) == 1
    parsed = urlsplit(transport.calls[0][0])
    assert parsed.hostname == "routing.openstreetmap.de"
    assert "Berlin" not in transport.calls[0][0] and "Munich" not in transport.calls[0][0]


def check_other_requires_manual_values():
    result = TransportSuggestionService(now=lambda: NOW).suggest(request("other"))
    assert result.status == "manual_required"
    assert result.time_hours is None and result.travel_days is None and result.search_url is None


if __name__ == "__main__":
    check_default_is_local_and_user_confirmed()
    check_links_are_coordinate_only_and_allowlisted()
    check_input_and_url_fail_closed()
    check_optional_osrm_is_disabled_and_falls_back()
    check_optional_osrm_contract_and_response_sanitization()
    check_other_requires_manual_values()
    print("PASS: trip transport suggestions are anonymous, read-only and fail closed")
