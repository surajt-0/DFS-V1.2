"""
Generic export helpers for artifact tables. Exports always run against the
*filtered* queryset the examiner is currently looking at (same search terms
applied), and never un-mask a protected column -- the values stored in the
DB for password/cookie value are already the literal string "Protected",
so there's no separate masking step needed at export time.
"""
from __future__ import annotations
import csv
import io
import json

from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook


def _row_values(obj, fields):
    out = []
    for f in fields:
        val = getattr(obj, f)
        if hasattr(val, "isoformat"):
            # val is an aware UTC datetime (USE_TZ=True stores everything in
            # UTC); strftime()-ing it directly prints the UTC clock time
            # verbatim instead of the configured local time, which is why
            # exported timestamps looked hours off from the rest of the app
            # (PDF reports, the UI) -- convert first, same as cases/report.py.
            val = timezone.localtime(val).strftime("%Y-%m-%d %H:%M:%S")
        out.append("" if val is None else val)
    return out


def export_csv(queryset, fields, headers, filename):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
    writer = csv.writer(response)
    writer.writerow(headers)
    for obj in queryset.iterator(chunk_size=1000):
        writer.writerow(_row_values(obj, fields))
    return response


def export_json(queryset, fields, headers, filename):
    data = []
    for obj in queryset.iterator(chunk_size=1000):
        data.append(dict(zip(headers, [str(v) for v in _row_values(obj, fields)])))
    response = HttpResponse(json.dumps(data, indent=2), content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="{filename}.json"'
    return response


def export_xlsx(queryset, fields, headers, filename):
    wb = Workbook()
    ws = wb.active
    ws.title = "Export"
    ws.append(list(headers))
    for obj in queryset.iterator(chunk_size=1000):
        ws.append([str(v) for v in _row_values(obj, fields)])
    buf = io.BytesIO()
    wb.save(buf)
    response = HttpResponse(
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
    return response


EXPORTERS = {"csv": export_csv, "xlsx": export_xlsx, "json": export_json}


def stamped_filename(base):
    return f"{base}_{timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M%S')}"
