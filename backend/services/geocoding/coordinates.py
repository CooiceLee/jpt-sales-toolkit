"""Coordinate conversion helpers. Business data always remains WGS84."""

from __future__ import annotations

import math


_A = 6378245.0
_EE = 0.006693421622965943


def _outside_china(lat: float, lng: float) -> bool:
    return not (73.66 <= lng <= 135.05 and 3.86 <= lat <= 53.55)


def _transform_lat(x: float, y: float) -> float:
    value = -100 + 2 * x + 3 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    value += (20 * math.sin(6 * x * math.pi) + 20 * math.sin(2 * x * math.pi)) * 2 / 3
    value += (20 * math.sin(y * math.pi) + 40 * math.sin(y / 3 * math.pi)) * 2 / 3
    return value + (160 * math.sin(y / 12 * math.pi) + 320 * math.sin(y * math.pi / 30)) * 2 / 3


def _transform_lng(x: float, y: float) -> float:
    value = 300 + x + 2 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    value += (20 * math.sin(6 * x * math.pi) + 20 * math.sin(2 * x * math.pi)) * 2 / 3
    value += (20 * math.sin(x * math.pi) + 40 * math.sin(x / 3 * math.pi)) * 2 / 3
    return value + (150 * math.sin(x / 12 * math.pi) + 300 * math.sin(x / 30 * math.pi)) * 2 / 3


def gcj02_to_wgs84(lat: float, lng: float) -> tuple[float, float]:
    if _outside_china(lat, lng):
        return lat, lng
    dlat = _transform_lat(lng - 105, lat - 35)
    dlng = _transform_lng(lng - 105, lat - 35)
    radlat = lat / 180 * math.pi
    magic = 1 - _EE * math.sin(radlat) ** 2
    sqrt_magic = math.sqrt(magic)
    dlat = dlat * 180 / ((_A * (1 - _EE)) / (magic * sqrt_magic) * math.pi)
    dlng = dlng * 180 / (_A / sqrt_magic * math.cos(radlat) * math.pi)
    return lat * 2 - (lat + dlat), lng * 2 - (lng + dlng)
