from __future__ import annotations

import ipaddress
import logging
from functools import lru_cache

from fastapi import Request

from ai_actuarial.config import settings

logger = logging.getLogger(__name__)
MAX_FORWARDED_HOPS = 32
MAX_FORWARDED_LENGTH = MAX_FORWARDED_HOPS * 64


def _address(value: str):
    # Scoped IPv6 addresses are not valid forwarded client identities.
    if "%" in value:
        raise ValueError("Scoped IP address")
    address = ipaddress.ip_address(value.strip())
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return address.ipv4_mapped
    return address


@lru_cache(maxsize=16)
def _trusted_networks(raw: str):
    try:
        networks = []
        for value in raw.split(","):
            network = ipaddress.ip_network(value.strip(), strict=False)
            if isinstance(network, ipaddress.IPv6Network):
                mapped = network.network_address.ipv4_mapped
                if mapped is not None and network.prefixlen >= 96:
                    network = ipaddress.ip_network((mapped, network.prefixlen - 96))
            networks.append(network)
        return tuple(networks)
    except ValueError:
        return ()


def validate_proxy_config() -> None:
    """Warn at application startup; missing/invalid allowlists disable forwarding."""
    if settings.TRUST_PROXY and not _trusted_networks(settings.TRUSTED_PROXY_CIDRS):
        logger.warning(
            "TRUST_PROXY is enabled but TRUSTED_PROXY_CIDRS is empty or invalid; "
            "forwarded headers will be ignored"
        )


def client_ip(request: Request) -> str:
    """Resolve the first untrusted hop, starting with the actual socket peer."""
    peer = request.client.host if request.client else None
    fallback = peer or "unknown"
    # Preserve the legacy socket-only behavior when trust is disabled.
    if not settings.TRUST_PROXY:
        return fallback
    try:
        address = _address(fallback)
    except ValueError:
        return fallback
    fallback = str(address)
    networks = _trusted_networks(settings.TRUSTED_PROXY_CIDRS)
    if not networks or not any(address in network for network in networks):
        return fallback

    # Include duplicate header fields in wire order; never truncate a chain.
    values = request.headers.getlist("X-Forwarded-For")
    if sum(map(len, values)) + len(values) > MAX_FORWARDED_LENGTH:
        return fallback
    parts = ",".join(values).split(",")
    if len(parts) > MAX_FORWARDED_HOPS:
        return fallback
    try:
        hops = [_address(part) for part in parts]
    except ValueError:
        return fallback
    for hop in reversed(hops):
        if not any(address in network for network in networks):
            break
        address = hop
    return str(address)
