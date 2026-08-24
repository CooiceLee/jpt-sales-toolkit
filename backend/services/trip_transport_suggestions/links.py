"""Construct only documented, user-opened HTTPS search URLs."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit


GOOGLE_MAPS_PATH = "/maps/dir/"
GOOGLE_FLIGHTS_PATH = "/travel/flights"
PUBLIC_LINKS = {
    ("www.google.com", GOOGLE_MAPS_PATH),
    ("www.google.com", GOOGLE_FLIGHTS_PATH),
}
OSRM_HOST = "routing.openstreetmap.de"
OSRM_PATH = "/routed-car/route/v1/driving/"
OSRM_COORDINATES_RE = re.compile(
    rf"^{re.escape(OSRM_PATH)}-?\d{{1,3}}\.\d{{6}},-?\d{{1,2}}\.\d{{6}};"
    r"-?\d{1,3}\.\d{6},-?\d{1,2}\.\d{6}$"
)


def validate_https_url(url: str, allowed: set[tuple[str, str]]) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("only allowlisted HTTPS URLs are permitted")
    if parsed.username or parsed.password or parsed.port is not None or parsed.fragment:
        raise ValueError("URL authority or fragment is not permitted")
    if (parsed.hostname, parsed.path) not in allowed:
        raise ValueError("URL host or path is not allowlisted")
    return url


def _point(lat: float, lng: float) -> str:
    return f"{lat:.6f},{lng:.6f}"


def maps_directions_url(request) -> str:
    travelmode = "transit" if request.mode == "ground_public" else "driving"
    query = urlencode(
        {
            "api": "1",
            "origin": _point(request.from_lat, request.from_lng),
            "destination": _point(request.to_lat, request.to_lng),
            "travelmode": travelmode,
        }
    )
    return validate_https_url(
        f"https://www.google.com{GOOGLE_MAPS_PATH}?{query}", PUBLIC_LINKS
    )


def flight_search_url() -> str:
    return validate_https_url(f"https://www.google.com{GOOGLE_FLIGHTS_PATH}", PUBLIC_LINKS)


def osrm_route_url(request) -> str:
    coordinates = (
        f"{request.from_lng:.6f},{request.from_lat:.6f};"
        f"{request.to_lng:.6f},{request.to_lat:.6f}"
    )
    url = f"https://{OSRM_HOST}{OSRM_PATH}{coordinates}?overview=false&steps=false"
    return validate_osrm_url(url)


def validate_osrm_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != OSRM_HOST:
        raise ValueError("OSRM URL is not allowlisted")
    if parsed.username or parsed.password or parsed.port is not None or parsed.fragment:
        raise ValueError("OSRM URL authority or fragment is not permitted")
    if not OSRM_COORDINATES_RE.fullmatch(parsed.path):
        raise ValueError("OSRM route path is not accepted")
    if parse_qsl(parsed.query, keep_blank_values=True) != [
        ("overview", "false"),
        ("steps", "false"),
    ]:
        raise ValueError("OSRM query is not accepted")
    return url
