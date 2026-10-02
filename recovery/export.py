"""CSV / XLSX / JSON export for recovery tables.

Unlike evidence/export.py (which exports queryset fields), these tables mix
stored rows and computed values, so this module takes plain header/row lists.

Recovered data is hostile input (URLs, titles, cookie names come straight
from evidence). Spreadsheet apps execute cells beginning with = + - @ as
formulas, so every text cell is neutralised with a leading apostrophe
(OWASP "CSV injection"); JSON is unaffected and left as-is.
"""
from __future__ import annotations

import csv
import io
import json

from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook

_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def _cell(v):
    if v is None:
        return ""
    if hasattr(v, "isoformat"):
        try:
            v = timezone.localtime(v).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            v = v.isoformat()
    if isinstance(v, (dict, list)):
        v = json.dumps(v, ensure_ascii=False, default=str)
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, (int, float)):
        return v
    v = str(v)
    return "'" + v if v.startswith(_DANGEROUS) else v


def stamped(base):
    return f"{base}_{timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M%S')}"


def build_response(fmt, headers, rows, filename):
    if fmt == "csv":
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
        w = csv.writer(resp)
        w.writerow(headers)
        for r in rows:
            w.writerow([_cell(v) for v in r])
        return resp
    if fmt == "json":
        data = []
        for r in rows:
            d = {}
            for h, v in zip(headers, r):
                if hasattr(v, "isoformat"):
                    v = _cell(v)
                d[h] = v
            data.append(d)
        resp = HttpResponse(json.dumps(data, indent=2, ensure_ascii=False, default=str),
                            content_type="application/json")
        resp["Content-Disposition"] = f'attachment; filename="{filename}.json"'
        return resp
    if fmt == "xlsx":
        wb = Workbook()
        ws = wb.active
        ws.title = "Export"
        ws.append(list(headers))
        for r in rows:
            ws.append([_cell(v) for v in r])
        buf = io.BytesIO()
        wb.save(buf)
        resp = HttpResponse(
            buf.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        resp["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
        return resp
    raise ValueError(fmt)
