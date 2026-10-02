"""OPTIONAL active DNS lookups.

This is the ONLY module in the suite that generates network traffic to
resolve names, and it is only invoked when the examiner explicitly asks
for it (evidence/recovery API: POST .../dns/lookup/). Why that matters:

  * A lookup can be logged by whoever runs the resolver/authoritative
    server and may alert a subject who monitors a domain they control.
  * Results describe DNS *today*, not what the subject's machine saw at
    the time of the events under investigation.

Both facts are surfaced in the UI and the results are labelled
`active_lookup` with the lookup time. Inputs are validated hostnames only
(never URLs / IPs / shell text) and the batch size is capped by the caller.
"""
from __future__ import annotations

import socket
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from dataclasses import dataclass, field
from typing import Optional

from .domains import is_valid_hostname

try:  # optional richer record types
    import dns.resolver as _dnsres  # type: ignore
    HAVE_DNSPYTHON = True
except Exception:  # pragma: no cover
    _dnsres = None
    HAVE_DNSPYTHON = False

TIMEOUT = 5.0


@dataclass
class LookupRecord:
    name: str
    record_type: str
    value: str
    ttl: Optional[int] = None


@dataclass
class LookupResult:
    name: str
    records: list = field(default_factory=list)
    error: str = ""


def _socket_lookup(name):
    recs = []
    seen = set()
    for fam, rtype in ((socket.AF_INET, "A"), (socket.AF_INET6, "AAAA")):
        try:
            for info in socket.getaddrinfo(name, None, fam, socket.SOCK_STREAM):
                ip = info[4][0]
                if (rtype, ip) not in seen:
                    seen.add((rtype, ip))
                    recs.append(LookupRecord(name, rtype, ip))
        except socket.gaierror:
            continue
    return recs


def _dnspython_lookup(name):
    recs = []
    res = _dnsres.Resolver()
    res.lifetime = TIMEOUT
    res.timeout = TIMEOUT
    for rtype in ("A", "AAAA", "CNAME", "MX", "NS", "TXT"):
        try:
            ans = res.resolve(name, rtype, raise_on_no_answer=False)
        except Exception:
            continue
        if ans.rrset is None:
            continue
        for r in ans:
            txt = r.to_text()
            if rtype == "TXT":
                txt = txt[:500]
            recs.append(LookupRecord(name, rtype, txt, ans.rrset.ttl))
    return recs


def lookup_domain(name: str) -> LookupResult:
    name = (name or "").strip().lower().rstrip(".")
    if not is_valid_hostname(name):
        return LookupResult(name, error="Not a valid hostname.")
    def fn(n):
        recs = _dnspython_lookup(n) if HAVE_DNSPYTHON else []
        # Fall back to the OS resolver (also honours this machine's hosts file).
        return recs or _socket_lookup(n)
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            recs = ex.submit(fn, name).result(timeout=TIMEOUT * 4)
    except FutTimeout:
        return LookupResult(name, error="Lookup timed out.")
    except Exception as exc:  # pragma: no cover - defensive
        return LookupResult(name, error=f"Lookup failed ({type(exc).__name__}).")
    if not recs:
        return LookupResult(name, error="No records found (NXDOMAIN or no data).")
    return LookupResult(name, recs)
