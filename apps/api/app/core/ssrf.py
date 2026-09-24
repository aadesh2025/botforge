"""SSRF guard shared by every code path that fetches a tenant-supplied URL."""

from __future__ import annotations

import ipaddress
import socket


def is_blocked_destination(host: str, allowed_hosts: str = "") -> bool:
    """`is_blocked_host`, except a host the operator named in `allowed_hosts` (comma-separated,
    exact hostname or IP literal, case-insensitive) is trusted. Only for destinations a tenant
    picked but the operator has vetted; every other caller uses `is_blocked_host` directly."""
    if host.lower() in {h.strip().lower() for h in allowed_hosts.split(",") if h.strip()}:
        return False
    return is_blocked_host(host)


def is_blocked_host(host: str) -> bool:
    """SSRF guard: reject loopback / private / link-local / reserved destinations."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return True
    return False
