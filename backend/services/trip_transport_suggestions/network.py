"""Restricted HTTPS JSON reader for explicitly enabled demo providers."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request

from .links import validate_osrm_url


class TransportProviderError(RuntimeError):
    pass


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise TransportProviderError("provider redirects are not accepted")


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except (ImportError, OSError):
        return ssl.create_default_context()


class RestrictedJsonClient:
    def __init__(self, timeout_seconds: float = 4.5, max_bytes: int = 256_000) -> None:
        self.timeout_seconds = min(8.0, max(0.5, float(timeout_seconds)))
        self.max_bytes = min(1_000_000, max(1_024, int(max_bytes)))
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=_ssl_context()), _RejectRedirects()
        )

    def get_osrm(self, url: str, user_agent: str) -> object:
        try:
            validate_osrm_url(url)
        except ValueError as exc:
            raise TransportProviderError("provider URL is not accepted") from exc
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "Accept-Encoding": "identity", "User-Agent": user_agent},
        )
        try:
            with self.opener.open(request, timeout=self.timeout_seconds) as response:
                content_type = response.headers.get_content_type()
                payload = response.read(self.max_bytes + 1)
        except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
            raise TransportProviderError("transport provider is unavailable") from exc
        if content_type != "application/json" or len(payload) > self.max_bytes:
            raise TransportProviderError("transport provider returned an invalid response")
        try:
            return json.loads(payload.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise TransportProviderError("transport provider returned invalid JSON") from exc
