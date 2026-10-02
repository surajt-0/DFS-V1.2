"""Hosts-file parsing and tamper heuristics.

A modified hosts file is a classic way to redirect banking/update/security
domains, or to silently block AV-update and telemetry hosts, so every entry
is classified:

  redirect_known_domain  a well-known brand domain mapped to a non-loopback
                         address  (possible phishing/redirect -> "alert")
  blocked_known_domain   a well-known domain mapped to 0.0.0.0/127.0.0.1/::1
                         (possible blocking of updates/security -> "warn")
  blocked                any other domain sinkholed to loopback  ("info";
                         typical of ad-block lists)
  normal                 ordinary local entry (localhost, LAN names)
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass

MAX_LINES = 200_000

WELL_KNOWN = {
    "google.com", "www.google.com", "gmail.com", "youtube.com", "facebook.com", "www.facebook.com",
    "microsoft.com", "www.microsoft.com", "login.microsoftonline.com", "live.com", "outlook.com",
    "windowsupdate.com", "update.microsoft.com", "apple.com", "www.apple.com", "icloud.com",
    "paypal.com", "www.paypal.com", "amazon.com", "www.amazon.com", "github.com", "twitter.com",
    "x.com", "instagram.com", "linkedin.com", "whatsapp.com", "dropbox.com", "netflix.com",
    "mozilla.org", "download.mozilla.org", "addons.mozilla.org", "update.googleapis.com",
    "clients2.google.com", "safebrowsing.googleapis.com", "virustotal.com", "kaspersky.com",
    "avast.com", "avg.com", "mcafee.com", "symantec.com", "norton.com", "bitdefender.com",
    "malwarebytes.com", "eset.com", "sophos.com", "sbi.co.in", "onlinesbi.com", "hdfcbank.com",
    "icicibank.com", "axisbank.com", "chase.com", "bankofamerica.com", "wellsfargo.com",
}
_LOOP = {"0.0.0.0", "127.0.0.1", "::1", "::", "0:0:0:0:0:0:0:1"}
_LOCAL_NAMES = {"localhost", "localhost.localdomain", "broadcasthost", "local", "ip6-localhost",
                "ip6-loopback", "ip6-localnet", "ip6-mcastprefix", "ip6-allnodes", "ip6-allrouters",
                "ip6-allhosts"}


@dataclass
class HostsEntry:
    ip: str
    hostname: str
    line_no: int
    flag: str       # normal | blocked | blocked_known_domain | redirect_known_domain
    severity: str   # info | warn | alert
    comment: str = ""


def _norm_ip(s):
    try:
        return str(ipaddress.ip_address(s.split("%")[0]))
    except ValueError:
        return None


def parse_hosts(text: str) -> list:
    out = []
    for n, raw in enumerate(text.splitlines()[:MAX_LINES], 1):
        line, _, comment = raw.partition("#")
        parts = line.split()
        if len(parts) < 2:
            continue
        ip = _norm_ip(parts[0])
        if ip is None:
            continue
        for name in parts[1:]:
            h = name.lower().rstrip(".")
            if not re.match(r"^[a-z0-9_.-]{1,253}$", h):
                continue
            loop = ip in {_norm_ip(x) for x in _LOOP}
            known = h in WELL_KNOWN or any(h.endswith("." + k) for k in WELL_KNOWN if k.count(".") == 1)
            if h in _LOCAL_NAMES or (not loop and ipaddress.ip_address(ip).is_private and "." not in h):
                flag, sev = "normal", "info"
            elif known and not loop:
                flag, sev = "redirect_known_domain", "alert"
            elif known and loop:
                flag, sev = "blocked_known_domain", "warn"
            elif loop:
                flag, sev = "blocked", "info"
            else:
                flag, sev = "normal", "info"
            out.append(HostsEntry(ip, h, n, flag, sev, comment.strip()[:200]))
    return out
