"""Thin HTTP fetcher with timeout and retry (standard library only)."""

import asyncio
import urllib.request
from urllib.parse import urlparse

ALLOWED_HOSTS = {"sachet.ndma.gov.in"}
USER_AGENT = "disaster-response-backend/ingestion (+https://sachet.ndma.gov.in)"
MAX_BYTES = 5_000_000


class FetchError(Exception):
    """Fetching failed. error_class names the underlying exception type only."""

    def __init__(self, error_class: str) -> None:
        super().__init__(error_class)
        self.error_class = error_class


def _get(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (host checked)
        payload = response.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError("Response too large.")
    return payload


async def fetch_bytes(
    url: str, *, timeout: float = 15.0, retries: int = 2, backoff_seconds: float = 1.0
) -> bytes:
    # Links come from feed content, so only the source's own host is fetched.
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise FetchError("DisallowedUrl")
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return await asyncio.to_thread(_get, url, timeout)
        except Exception as exc:  # network, HTTP and size errors are all retried
            last = exc
            if attempt < retries:
                await asyncio.sleep(backoff_seconds * (2 ** attempt))
    raise FetchError(type(last).__name__)
