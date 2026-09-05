"""
Resilient asynchronous HTTP client with per-source token-bucket rate limiting,
exponential backoff, retry handling, and connection pooling.
"""

from __future__ import annotations
import asyncio
import ipaddress
import random
import socket
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse
import httpx


def is_safe_public_url(url: str) -> bool:
    """
    Validates that a URL uses http/https and does NOT point to localhost,
    private LAN, link-local, cloud metadata (169.254.169.254), or reserved IP spaces.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme.lower() not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False

        lower_host = hostname.lower().strip("[]")
        if lower_host in ("localhost", "localhost.localdomain", "broadcasthost", "0.0.0.0"):
            return False

        addr_info = socket.getaddrinfo(lower_host, None)
        for item in addr_info:
            ip_str = item[4][0]
            ip = ipaddress.ip_address(ip_str)
            if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
                ip = ip.ipv4_mapped

            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                return False
        return True
    except Exception:
        return False


def validate_safe_url(url: str) -> str:
    """Raises ValueError if URL violates SSRF safety constraints."""
    if not is_safe_public_url(url):
        raise ValueError(
            f"SSRF Protection: URL '{url}' is invalid or targets a non-public/private network."
        )
    return url


class TokenBucketRateLimiter:
    """Token bucket algorithm for smooth, burst-limited rate control per source."""

    def __init__(self, rate_per_second: float = 5.0, burst: int = 10):
        self.rate = rate_per_second
        self.capacity = float(burst)
        self.tokens = float(burst)
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        while True:
            wait_time = 0.0
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self.last_update
                self.last_update = now
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)

                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                wait_time = (1.0 - self.tokens) / self.rate
            # Sleep OUTSIDE the lock so concurrent requests on this client
            # are not serialized behind a single sleeping waiter.
            await asyncio.sleep(wait_time)


class ResilientHttpClient:
    """Async HTTP client with backoff retries, connection pooling, and rate limits."""

    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 (OmniSearchBot/2.0)"
    )

    def __init__(
        self,
        timeout_seconds: float = 12.0,
        max_retries: int = 3,
        rate_limit_per_sec: float = 5.0,
    ):
        self.timeout = timeout_seconds
        self.max_retries = max_retries
        self.rate_limiter = TokenBucketRateLimiter(rate_per_second=rate_limit_per_sec, burst=10)
        self._client: Optional[httpx.AsyncClient] = None

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)
            headers = {
                "User-Agent": self.DEFAULT_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
                "Accept-Language": "en-US,en;q=0.9",
            }
            self._client = httpx.AsyncClient(
                headers=headers,
                limits=limits,
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
            )
        return self._client

    async def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        safe_only: bool = False,
    ) -> httpx.Response:
        """Performs a GET request with rate limiting and exponential backoff on transient errors."""
        return await self._request("GET", url, params=params, headers=headers, timeout=timeout, safe_only=safe_only)

    async def post(
        self,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        safe_only: bool = False,
    ) -> httpx.Response:
        """Performs a POST request with rate limiting and exponential backoff on transient errors."""
        return await self._request("POST", url, params=params, data=data, headers=headers, timeout=timeout, safe_only=safe_only)

    async def _request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        safe_only: bool = False,
    ) -> httpx.Response:
        """Core request loop with rate limiting, retries, and SSRF-safe redirect handling."""
        client = await self.get_client()
        last_exception: Optional[Exception] = None
        current_url = url

        if safe_only:
            validate_safe_url(current_url)

        max_redirects = 5 if safe_only else 0
        redirect_count = 0

        while True:
            for attempt in range(self.max_retries + 1):
                await self.rate_limiter.acquire()
                try:
                    t = timeout or self.timeout
                    resp = await client.request(
                        method,
                        current_url,
                        params=params if redirect_count == 0 else None,
                        data=data if redirect_count == 0 else None,
                        headers=headers,
                        timeout=t,
                        follow_redirects=not safe_only,
                    )

                    if resp.status_code == 429 or resp.status_code in (500, 502, 503, 504):
                        if attempt < self.max_retries:
                            retry_after = resp.headers.get("Retry-After")
                            if retry_after and retry_after.isdigit():
                                wait = float(retry_after)
                            else:
                                wait = (2.0 ** attempt) * 0.5 + random.uniform(0.1, 0.5)
                            await asyncio.sleep(wait)
                            continue

                    if safe_only and resp.is_redirect:
                        location = resp.headers.get("Location")
                        if not location:
                            return resp
                        next_url = str(resp.url.join(location))
                        validate_safe_url(next_url)
                        redirect_count += 1
                        if redirect_count > max_redirects:
                            raise httpx.TooManyRedirects(
                                "Too many redirects", request=resp.request, response=resp
                            )
                        current_url = next_url
                        break
                    return resp
                except (httpx.ConnectError, httpx.ReadTimeout, httpx.PoolTimeout, httpx.RemoteProtocolError) as exc:
                    last_exception = exc
                    if attempt < self.max_retries:
                        wait = (2.0 ** attempt) * 0.5 + random.uniform(0.1, 0.4)
                        await asyncio.sleep(wait)
                    else:
                        raise exc
            else:
                if last_exception:
                    raise last_exception
                raise httpx.RequestError("Request failed after retries", request=None)

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

