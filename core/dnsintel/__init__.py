"""DNS details for forensic examination (Django-free, like core/parsers).

  hosts.py     parse a hosts file and flag tampering (redirected well-known
               domains, blackholed domains)
  resolver.py  parse resolver configuration and DNS-cache dumps from
               Windows / macOS / Linux, and collect them from THIS machine
  lookup.py    OPTIONAL active DNS lookups (only ever run on an explicit
               examiner request -- see the module docstring)
  domains.py   domain extraction / grouping from browser artifacts

Passive by default: nothing in this package touches the network unless
lookup.py is called, which the API only does when the examiner asks.
"""
