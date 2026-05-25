from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import Callable
from urllib.parse import unquote, urlsplit


class UnsafeUrlError(ValueError):
    """Raised when a URL is not safe to fetch."""


Resolver = Callable[..., list[tuple]]


@dataclass(frozen=True)
class SafeUrlResolution:
    url: str
    host: str
    addresses: tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]


_ALLOWED_SCHEMES = {"http", "https"}
_HEX_RE = re.compile(r"^0x[0-9a-f]+$", re.IGNORECASE)
_OCTAL_RE = re.compile(r"^0[0-7]+$")
_DECIMAL_RE = re.compile(r"^[0-9]+$")


def ensure_safe_http_url(url: str, *, resolver: Resolver | None = None) -> str:
    return resolve_safe_http_url(url, resolver=resolver).url


def resolve_safe_http_url(url: str, *, resolver: Resolver | None = None) -> SafeUrlResolution:
    candidate = str(url or "").strip()
    try:
        parsed = urlsplit(candidate)
    except ValueError as exc:
        raise UnsafeUrlError(f"Invalid URL: {exc}") from exc
    scheme = parsed.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"URL scheme '{parsed.scheme or '<missing>'}' is not allowed")

    host = _normalized_host(parsed.hostname)
    try:
        parsed.port
    except ValueError as exc:
        raise UnsafeUrlError(f"Invalid URL port: {exc}") from exc
    if not host:
        raise UnsafeUrlError("URL host is required")
    if host == "localhost":
        raise UnsafeUrlError("localhost is not allowed")

    addresses = tuple(_resolved_ip_addresses(host, resolver=resolver))
    for address in addresses:
        if _is_disallowed_ip(address):
            raise UnsafeUrlError(f"URL resolves to a non-public IP address: {address}")

    return SafeUrlResolution(url=candidate, host=host, addresses=addresses)


def _normalized_host(host: str | None) -> str:
    if not host:
        return ""
    return unquote(host).strip().rstrip(".").lower()


def _resolved_ip_addresses(host: str, *, resolver: Resolver | None = None) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    direct_ip = _parse_ip_literal(host)
    if direct_ip is not None:
        return [direct_ip]

    lookup = resolver or socket.getaddrinfo
    try:
        infos = lookup(host, None, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"Failed to resolve host '{host}': {exc}") from exc

    for family, _, _, _, sockaddr in infos:
        if family not in (socket.AF_INET, socket.AF_INET6):
            continue
        raw_ip = str(sockaddr[0])
        try:
            addresses.append(ipaddress.ip_address(raw_ip.split('%', 1)[0]))
        except ValueError:
            continue

    if not addresses:
        raise UnsafeUrlError(f"Host '{host}' did not resolve to an IP address")
    return addresses


def _parse_ip_literal(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass

    try:
        if _DECIMAL_RE.fullmatch(host):
            value = int(host, 10)
            if 0 <= value <= (2**32 - 1):
                return ipaddress.IPv4Address(value)
        if _HEX_RE.fullmatch(host):
            value = int(host, 16)
            if 0 <= value <= (2**32 - 1):
                return ipaddress.IPv4Address(value)
        if _OCTAL_RE.fullmatch(host):
            value = int(host, 8)
            if 0 <= value <= (2**32 - 1):
                return ipaddress.IPv4Address(value)
    except ValueError:
        return None

    return None


def _is_disallowed_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        str(address) == "169.254.169.254"
        or address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        or not address.is_global
    )
