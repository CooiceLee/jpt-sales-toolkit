"""Provider-neutral geocoding package."""

from .amap import AmapProvider
from .coordinator import GeocodingCoordinator
from .errors import GeocodingError
from .factory import get_geocoding_coordinator, reset_geocoding_coordinator
from .models import GeocodeCandidate, GeocodeQuery, GeocodeSearchResult
from .nominatim import NominatimProvider

__all__ = [
    "AmapProvider", "GeocodingCoordinator", "GeocodingError",
    "GeocodeCandidate", "GeocodeQuery", "GeocodeSearchResult",
    "NominatimProvider", "get_geocoding_coordinator", "reset_geocoding_coordinator",
]
