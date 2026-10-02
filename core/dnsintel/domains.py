"""Host / registrable-domain extraction from URLs."""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

# Common multi-label public suffixes. Not the full PSL (no network/data file
# dependency in a forensic tool); unknown suffixes fall back to the last two
# labels, which is right for the overwhelming majority of hosts.
_SLD = {"co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "net.au", "org.au", "co.in", "net.in", "org.in",
        "gov.in", "ac.in", "co.jp", "com.br", "com.cn", "com.mx", "co.za", "co.nz", "com.sg", "com.hk",
        "com.tr", "com.ar", "co.kr", "com.tw", "com.my", "com.pk", "co.id"}
_LABEL = re.compile(r"^(?!-)[a-z0-9_-]{1,63}(?<!-)$")


def host_of(url: str):
    """Lower-cased hostname of an http(s)/ftp/ws URL, else None."""
    try:
        parts = urlsplit((url or "").strip())
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https", "ftp", "ws", "wss"):
        return None
    try:
        host = parts.hostname
    except ValueError:
        return None
    return host.lower().rstrip(".") if host else None


def is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def is_valid_hostname(host: str) -> bool:
    if not host or len(host) > 253 or is_ip(host):
        return False
    labels = host.lower().rstrip(".").split(".")
    if labels[-1].isdigit():   # a TLD is never all digits -> this is a malformed IP, not a hostname
        return False
    return all(_LABEL.match(l) for l in labels)


def registrable(host: str) -> str:
    if not host or is_ip(host):
        return host
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    if ".".join(labels[-2:]) in _SLD and len(labels) >= 3:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def host_from_cookie_domain(d: str):
    d = (d or "").strip().lstrip(".").lower()
    return d if is_valid_hostname(d) else None
