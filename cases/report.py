"""
Generates a professional, timestamped chain-of-custody PDF report for a
case using reportlab (pure-Python, no system dependencies) -- includes
case metadata, examiner info, and every evidence item with its SHA-256
hash and parse status.
"""
from __future__ import annotations
import io

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)

_INK = colors.HexColor("#0d1117")
_TEAL = colors.HexColor("#2dd4bf")
_GREY = colors.HexColor("#8b949e")


def _append_recovery_section(story, case, h2, body):
    """Deleted-data / system-data / DNS summary. Silent when the examiner
    never ran any of those modules for this case."""
    from django.db.models import Count
    from recovery.models import DnsEntry, RecoveredRecord, RecoveryRun, StateItem

    runs = list(RecoveryRun.objects.filter(case=case).select_related("evidence").order_by("created_at"))
    state_n = StateItem.objects.filter(evidence__case=case).count()
    dns_n = DnsEntry.objects.filter(case=case).count()
    if not (runs or state_n or dns_n):
        return
    small = ParagraphStyle("recsmall", parent=body, fontSize=8, textColor=_GREY)
    story.append(Paragraph("Recovered &amp; Supplementary Data", h2))

    if runs:
        latest = {}
        for r in runs:                       # last run per evidence item wins
            latest[r.evidence_id] = r
        rows = [["Evidence file", "Run at", "Result", "Found", "High", "Med", "Low", "WAL"]]
        for r in latest.values():
            conf = {c["confidence"]: c["n"] for c in RecoveredRecord.objects.filter(run=r)
                    .values("confidence").annotate(n=Count("id"))}
            rows.append([Paragraph(r.evidence.original_filename, body),
                         timezone.localtime(r.created_at).strftime("%Y-%m-%d %H:%M"),
                         r.get_status_display(), str(r.records_found), str(conf.get("high", 0)),
                         str(conf.get("medium", 0)), str(conf.get("low", 0)), "yes" if r.wal_used else "no"])
        t = Table(rows, colWidths=[52*mm, 27*mm, 30*mm, 13*mm, 12*mm, 12*mm, 12*mm, 12*mm], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _INK), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d1d5db")),
            ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(Paragraph("Deleted-record recovery (SQLite free pages, freeblocks and WAL)", body))
        story.append(Spacer(1, 2 * mm))
        story.append(t)
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(
            "Recovered rows are remnants of deleted data. Confidence: <b>high</b> = complete, integrity-checked "
            "record; <b>medium</b> = decoded and validated; <b>low</b> = header reconstructed from the table "
            "schema (verify before relying on it). Passwords and cookie values are never recovered.", small))
    if state_n:
        cats = {c["category"]: c["n"] for c in StateItem.objects.filter(evidence__case=case)
                .values("category").annotate(n=Count("id"))}
        closed = StateItem.objects.filter(evidence__case=case, status="recovered_closed").count()
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(
            "Browser system data: " + ", ".join(f"{n} {c}" for c, n in sorted(cats.items()))
            + (f" (including {closed} recently-closed tab entries)" if closed else "") + ".", body))
    if dns_n:
        alerts = DnsEntry.objects.filter(case=case, severity="alert").count()
        lk = DnsEntry.objects.filter(case=case, origin="active_lookup")
        lookups = lk.count()
        last_lookup = lk.order_by("-observed_at").values_list("observed_at", flat=True).first()
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(
            f"DNS details: {dns_n} entries recorded, {alerts} hosts-file alert(s)."
            + (f" {lookups} rows come from active lookups (latest "
               f"{timezone.localtime(last_lookup).strftime('%Y-%m-%d %H:%M')}) and describe DNS at lookup "
               "time, not at the time of the events under investigation." if lookups else ""), body))


def build_case_report_pdf(case) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=22 * mm, bottomMargin=18 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
        title=f"Case Report - {case.case_number}",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("SuiteTitle", parent=styles["Title"], textColor=_INK, fontSize=20)
    sub_style = ParagraphStyle("SuiteSub", parent=styles["Normal"], textColor=_GREY, fontSize=10)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=_INK, spaceBefore=14)
    body = styles["Normal"]

    story = []
    story.append(Paragraph("Digital Forensics Browser Suite", sub_style))
    story.append(Paragraph(f"Case Report &mdash; {case.case_number}", title_style))
    story.append(Paragraph(case.name, sub_style))
    story.append(Spacer(1, 10 * mm))

    meta_rows = [
        ["Investigator", case.investigator.get_full_name() or case.investigator.get_username()],
        ["Status", case.get_status_display()],
        ["Priority", case.get_priority_display()],
        ["Subject / Custodian", case.subject_name or "-"],
        ["Case created", timezone.localtime(case.created_at).strftime("%Y-%m-%d %H:%M:%S")],
        ["Report generated", timezone.localtime().strftime("%Y-%m-%d %H:%M:%S")],
        ["Evidence items", str(case.evidence_count)],
        ["Tags", ", ".join(case.tag_list) or "-"],
    ]
    meta_table = Table(meta_rows, colWidths=[45 * mm, 120 * mm])
    meta_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), _GREY),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#e5e7eb")),
    ]))
    story.append(meta_table)

    if case.description:
        story.append(Paragraph("Description", h2))
        story.append(Paragraph(case.description.replace("\n", "<br/>"), body))

    story.append(Paragraph("Evidence &amp; Chain of Custody", h2))
    ev_header = ["#", "Filename", "Type", "SHA-256", "Size", "Status", "Uploaded"]
    ev_rows = [ev_header]
    for i, item in enumerate(case.evidence_items.all().order_by("uploaded_at"), start=1):
        ev_rows.append([
            str(i),
            Paragraph(item.original_filename, body),
            item.get_evidence_type_display(),
            Paragraph(item.sha256 or "-", ParagraphStyle("mono", parent=body, fontName="Courier", fontSize=6.5)),
            f"{item.size_bytes:,} B",
            item.get_status_display(),
            timezone.localtime(item.uploaded_at).strftime("%Y-%m-%d %H:%M"),
        ])
    if len(ev_rows) == 1:
        ev_rows.append(["-", "No evidence registered yet.", "", "", "", "", ""])

    ev_table = Table(ev_rows, colWidths=[8*mm, 42*mm, 24*mm, 45*mm, 18*mm, 18*mm, 22*mm], repeatRows=1)
    ev_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d1d5db")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fb")]),
    ]))
    story.append(ev_table)

    _append_recovery_section(story, case, h2, body)

    story.append(Spacer(1, 10 * mm))
    footer = (
        "Generated by Digital Forensics Browser Suite (Web Edition) &mdash; Agamya Cyber Tech. "
        "SHA-256 hashes were computed at the moment each item was registered as evidence in this case. "
        "Passwords and cookie values are never extracted in cleartext by this suite."
    )
    story.append(Paragraph(footer, ParagraphStyle("footer", parent=body, fontSize=7.5, textColor=_GREY)))

    doc.build(story)
    return buf.getvalue()
