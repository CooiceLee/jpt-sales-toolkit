"""Small HTTPS JSON client with frozen-app certificate support."""

from __future__ import annotations

import json
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request

from .errors import GeocodingError


def trusted_ssl_context() -> ssl.SSLContext:
    """Prefer the bundled certifi store, then the operating-system default."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except (ImportError, OSError):
        return ssl.create_default_context()


class JsonTransport:
    def __init__(self, timeout_seconds: float = 12.0) -> None:
        self.timeout_seconds = timeout_seconds
        self.ssl_context = trusted_ssl_context()

    def get(self, url: str, params: dict, headers: dict, provider: str) -> object:
        target = f"{url}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(target, headers=headers)
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
                context=self.ssl_context,
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise GeocodingError(
                    "provider_auth", "Map service authorization failed.",
                    status_code=502, retryable=False, provider=provider,
                ) from exc
            if exc.code == 429:
                raise GeocodingError(
                    "provider_quota", "Map service request limit reached. Try again later.",
                    status_code=429, provider=provider,
                ) from exc
            raise GeocodingError(
                "provider_error", "Map service is temporarily unavailable.",
                status_code=502, provider=provider,
            ) from exc
        except ssl.SSLCertVerificationError as exc:
            raise GeocodingError(
                "tls_error", "Secure connection to the map service could not be verified.",
                provider=provider,
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise GeocodingError(
                "timeout", "Map service timed out. Try again.", provider=provider,
            ) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, ssl.SSLCertVerificationError):
                code = "tls_error"
                message = "Secure connection to the map service could not be verified."
            else:
                code = "network_error"
                message = "Map service could not be reached. Check the network and retry."
            raise GeocodingError(code, message, provider=provider) from exc
        except OSError as exc:
            raise GeocodingError(
                "network_error", "Map service could not be reached. Check the network and retry.",
                provider=provider,
            ) from exc
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise GeocodingError(
                "invalid_response", "Map service returned an invalid response.",
                status_code=502, provider=provider,
            ) from exc
