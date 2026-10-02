"""Resolver configuration + DNS-cache parsing / local collection.

Parsers take TEXT (so uploaded exports and live command output share one
code path); `collect_local()` runs a fixed, argument-free set of OS
commands with a timeout -- no user-supplied input ever reaches a shell.

Recognised formats
  resolv.conf                       (Linux/macOS)
  `ipconfig /displaydns`            (Windows DNS client cache)
  `resolvectl status`               (systemd-resolved)
  `scutil --dns`                    (macOS)
  `resolvectl show-cache` / `dscacheutil` are not universally available and
  are intentionally not required.
"""
from __future__ import annotations

import platform
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

MAX_TEXT = 32 * 1024 * 1024


@dataclass
class DnsRow:
    entry_type: str       # cache | resolver | search_domain | dns_setting | hosts
    name: str
    value: str = ""
    record_type: str = ""
    ttl: Optional[int] = None
    detail: dict = field(default_factory=dict)


def _clip(s, n=500):
    return (s or "")[:n]


def parse_resolv_conf(text: str) -> list:
    rows = []
    for raw in text.splitlines()[:5000]:
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        key = parts[0].lower()
        if key == "nameserver" and len(parts) >= 2:
            rows.append(DnsRow("resolver", "nameserver", _clip(parts[1])))
        elif key in ("search", "domain") and len(parts) >= 2:
            for d in parts[1:]:
                rows.append(DnsRow("search_domain", _clip(d)))
        elif key == "options":
            rows.append(DnsRow("dns_setting", "options", _clip(" ".join(parts[1:]))))
    return rows


_WIN_KV = re.compile(r"^\s*([A-Za-z()\- ]+?)[ .]*:\s*(.*)$")
_WIN_TYPES = {"a (host) record": "A", "aaaa record": "AAAA", "cname record": "CNAME", "ptr record": "PTR",
              "mx record": "MX", "ns record": "NS", "txt record": "TXT", "soa record": "SOA", "srv record": "SRV"}


def parse_ipconfig_displaydns(text: str) -> list:
    rows, cur = [], {}

    def flush():
        if cur.get("name") and cur.get("data"):
            for rtype, data in cur["data"]:
                rows.append(DnsRow("cache", _clip(cur["name"]), _clip(data), rtype,
                                   cur.get("ttl"), {"section": cur.get("section", "")}))
    for raw in text.splitlines()[:400_000]:
        m = _WIN_KV.match(raw)
        if not m:
            if not raw.strip() and cur.get("name") and cur.get("data"):
                flush()
                cur = {}
            continue
        k, v = m.group(1).strip().lower(), m.group(2).strip()
        if k == "record name":
            if cur.get("name") and cur.get("data"):
                flush()
            cur = {"name": v, "data": []}
        elif k == "time to live":
            try:
                cur["ttl"] = int(v)
            except ValueError:
                pass
        elif k == "section":
            cur["section"] = v
        elif k in _WIN_TYPES and cur:
            cur.setdefault("data", []).append((_WIN_TYPES[k], v))
    flush()
    return rows


def parse_resolvectl_status(text: str) -> list:
    rows, link = [], "Global"
    for raw in text.splitlines()[:20000]:
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^(Global|Link \d+ \(.+\))$", line)
        if m:
            link = m.group(1)
            continue
        m = re.match(r"^(Current DNS Server|DNS Servers?|DNS Domain|Fallback DNS Servers|Protocols|DNS Over TLS|"
                     r"DNSSEC|DNSSEC supported|resolv\.conf mode|LLMNR setting|MulticastDNS setting|"
                     r"DefaultRoute setting|Current Scopes):\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        if key in ("Current DNS Server", "DNS Server", "DNS Servers", "Fallback DNS Servers"):
            for ip in val.split():
                rows.append(DnsRow("resolver", key, _clip(ip), detail={"link": link}))
        elif key == "DNS Domain":
            for d in val.split():
                rows.append(DnsRow("search_domain", _clip(d), detail={"link": link}))
        else:
            rows.append(DnsRow("dns_setting", key, _clip(val), detail={"link": link}))
    return rows


def parse_scutil_dns(text: str) -> list:
    rows, res = [], ""
    for raw in text.splitlines()[:20000]:
        line = raw.strip()
        m = re.match(r"^resolver #(\d+)", line)
        if m:
            res = m.group(1)
            continue
        m = re.match(r"^nameserver\[(\d+)\]\s*:\s*(\S+)", line)
        if m:
            rows.append(DnsRow("resolver", "nameserver", _clip(m.group(2)), detail={"resolver": res}))
            continue
        m = re.match(r"^search domain\[(\d+)\]\s*:\s*(\S+)", line)
        if m:
            rows.append(DnsRow("search_domain", _clip(m.group(2)), detail={"resolver": res}))
            continue
        m = re.match(r"^(domain|flags|reach|if_index)\s*:\s*(.*)$", line)
        if m:
            rows.append(DnsRow("dns_setting", m.group(1), _clip(m.group(2)), detail={"resolver": res}))
    return rows


def sniff_and_parse(text: str) -> list:
    """Best-effort format detection for an uploaded text export."""
    t = text[:MAX_TEXT]
    if re.search(r"Record Name\s*[. ]*:", t):
        return parse_ipconfig_displaydns(t)
    if re.search(r"^resolver #\d+", t, re.M):
        return parse_scutil_dns(t)
    if re.search(r"^(Global|Link \d+ \()", t, re.M) and "DNS" in t:
        return parse_resolvectl_status(t)
    if re.search(r"^\s*nameserver\s+\S+", t, re.M):
        return parse_resolv_conf(t)
    return []


# ---------------------------------------------------------------------------
# Local machine collection
# ---------------------------------------------------------------------------
def _run(argv, timeout=15):
    try:
        cp = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, shell=False,
                            errors="replace")
        return cp.stdout if cp.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def hosts_file_path() -> Path:
    if platform.system() == "Windows":
        import os
        return Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "drivers" / "etc" / "hosts"
    return Path("/etc/hosts")


def collect_local() -> dict:
    """-> {"platform", "rows": [DnsRow], "hosts_text": str, "notes": [str]}"""
    system = platform.system()
    rows, notes = [], []
    if system == "Windows":
        out = _run(["ipconfig", "/displaydns"])
        if out:
            rows += parse_ipconfig_displaydns(out)
        else:
            notes.append("Couldn't read the Windows DNS client cache (ipconfig /displaydns).")
    elif system == "Darwin":
        out = _run(["scutil", "--dns"])
        rows += parse_scutil_dns(out) if out else []
        if not out:
            notes.append("Couldn't run scutil --dns.")
        notes.append("macOS does not expose its DNS cache contents to unprivileged tools; only resolver "
                     "configuration was collected.")
    else:
        out = _run(["resolvectl", "status"]) or _run(["systemd-resolve", "--status"])
        if out:
            rows += parse_resolvectl_status(out)
        try:
            rows += parse_resolv_conf(Path("/etc/resolv.conf").read_text(errors="replace"))
        except OSError:
            notes.append("Couldn't read /etc/resolv.conf.")
        notes.append("Linux does not keep a system-wide DNS cache readable by unprivileged tools; only "
                     "resolver configuration was collected.")
    hosts_text = ""
    try:
        hosts_text = hosts_file_path().read_text(errors="replace")[:MAX_TEXT]
    except OSError:
        notes.append("Couldn't read the hosts file.")
    return {"platform": system, "rows": rows, "hosts_text": hosts_text, "notes": notes}
