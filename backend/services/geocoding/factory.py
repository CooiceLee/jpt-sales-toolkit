"""Build the process-wide coordinator from local runtime settings."""

from __future__ import annotations

import os
from functools import lru_cache

from ...config import APP_VERSION, get_settings
from .amap import AmapProvider
from .cache import GeocodeCache
from .coordinator import GeocodingCoordinator
from .nominatim import NominatimProvider


@lru_cache(maxsize=1)
def get_geocoding_coordinator() -> GeocodingCoordinator:
    settings = get_settings()
    amap = AmapProvider(os.environ.get("JPT_AMAP_WEB_SERVICE_KEY"))
    global_provider = NominatimProvider(f"JPTSalesToolkit/{APP_VERSION}")
    preferred = os.environ.get("JPT_GEOCODING_PROVIDER", "nominatim").strip().lower()
    # Amap is opt-in. When selected, Nominatim remains the global fallback;
    # merely setting a key must not redirect otherwise global searches to Amap.
    providers = [amap, global_provider] if preferred == "amap" and amap.enabled else [global_provider]
    return GeocodingCoordinator(
        providers,
        GeocodeCache(settings.data_dir / "cache" / "geocoding.sqlite3"),
    )


def reset_geocoding_coordinator() -> None:
    """Testing and runtime-reconfiguration hook."""
    get_geocoding_coordinator.cache_clear()
