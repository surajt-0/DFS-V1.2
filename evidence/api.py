import shutil
import uuid
from pathlib import Path

from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from auditlog.utils import log_action
from billing.access import evidence_limit_status, has_feature, is_org_read_only, org_of
from billing.exceptions import PlanLimitExceeded
from cases.models import Case
from core.browser_detect import detect_all
from core.parsers.detect import detect_evidence_type
from core.permissions import require_edit, require_upload_evidence, require_view
from core.utils import sha256_of_file

from .forms import EvidenceUploadForm
from .localcopy import METHOD_DIRECT, copy_local_file
from .models import EvidenceItem
from .serializers import EvidenceItemSerializer
from .services import ParseError, load_demo_data, parse_evidence
from .table_config import EXPORT_FEATURE_MAP, SORT_WHITELIST, TABLE_CONFIG


class ArtifactPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


def _write_source_to(source, dest_path):
    """Copies bytes from either an uploaded multipart file (has .chunks())
    or a local filesystem Path (the local-scan path, reading directly off
    the examiner's own machine) into dest_path -- our own frozen snapshot,
    taken at read time, that parsing then runs against either way.

    Returns the copy method used ("direct" for uploads and ordinary local
    copies; see evidence/localcopy.py for the fallbacks used when a running
    browser has the file open). Reading a local Path can still raise
    OSError if every strategy fails; the caller reports that per-file
    rather than failing the whole batch."""
    if isinstance(source, Path):
        return copy_local_file(source, dest_path)
    with open(dest_path, "wb") as out:
        for chunk in source.chunks():
            out.write(chunk)
    return METHOD_DIRECT


def _ingest_evidence_file(request, case, filename, source, override_type, note):
    """Shared by EvidenceUploadAPI (manual multipart upload) and
    LocalScanAPI (reading files directly off the local machine's disk):
    copies the file into evidence_store, auto-detects its type when not
    overridden, and parses it. Returns a per-file result dict -- never
    raises for an ordinary bad/unreadable/unrecognized file, since the
    whole point is that one bad file in a batch shouldn't stop the rest,
    and manual upload is always available as a fallback for anything this
    can't handle."""
    dest_dir = Path(settings.EVIDENCE_STORAGE_ROOT) / str(case.pk)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{uuid.uuid4().hex}_{filename}"

    try:
        copy_method = _write_source_to(source, dest_path)
    except (OSError, PermissionError) as exc:
        dest_path.unlink(missing_ok=True)
        return {
            "original_filename": filename,
            "status": "rejected",
            "detail": (
                f"Couldn't read this file ({exc}). If it belongs to a browser that's currently "
                "running, close the browser and try again -- or export/copy the file elsewhere "
                "and upload it manually below."
            ),
        }

    detected = False
    etype = override_type
    if not etype:
        etype = detect_evidence_type(dest_path, filename)
        detected = etype is not None
    if not etype:
        etype = EvidenceItem.EvidenceType.OTHER

    # Re-run the same filename/extension sanity check the Django form
    # uses -- a no-op in the normal auto-detected case (content sniffing
    # already confirmed the match), still useful when a manual override
    # was supplied that clashes with the actual file. Only manual uploads
    # carry a real Django UploadedFile the form's FileField can validate
    # against; local-scan sources are plain Paths, already validated by
    # detect_evidence_type's content sniff, so there's nothing more to check.
    if hasattr(source, "chunks"):
        form = EvidenceUploadForm({"evidence_type": etype, "note": note}, {"file": source})
        if not form.is_valid():
            dest_path.unlink(missing_ok=True)
            return {"original_filename": filename, "status": "rejected", "detail": "; ".join(
                msg for errs in form.errors.values() for msg in errs
            )}

    if copy_method != METHOD_DIRECT:
        # How a copy was obtained matters in forensics: make a non-standard
        # (fallback) copy visible on the evidence record itself. The marker
        # is kept intact -- it's the user's free-text note that gets trimmed
        # to fit the 300-char column, never the marker.
        marker = f"[copied via {copy_method} while the source was in use"
        marker += "; newest not-yet-checkpointed rows may be missing]" if copy_method == "sqlite-snapshot" else "]"
        note = (note[: max(0, 300 - len(marker) - 1)] + " " + marker).strip()

    # A browser DB that was in use keeps its newest (and often its deleted)
    # rows in a -wal file next to it. Capture that companion next to our copy
    # (recovery/services.py looks for "<stored>-wal") and record its hash in
    # the note -- the WAL isn't a separate evidence item, so this is where its
    # chain of custody lives.
    if isinstance(source, Path):
        wal_src = Path(str(source) + "-wal")
        if wal_src.exists():
            wal_dest = Path(str(dest_path) + "-wal")
            try:
                copy_local_file(wal_src, wal_dest)
                wal_digest, _ = sha256_of_file(wal_dest)
                marker = f"[+WAL companion captured, sha256={wal_digest[:16]}...]"
                note = (note[: max(0, 300 - len(marker) - 1)] + " " + marker).strip()
            except OSError:
                wal_dest.unlink(missing_ok=True)

    digest, size = sha256_of_file(dest_path)
    evidence = EvidenceItem.objects.create(
        case=case,
        evidence_type=etype,
        note=note,
        original_filename=filename,
        stored_path=str(dest_path),
        sha256=digest,
        size_bytes=size,
        uploaded_by=request.user,
    )
    log_action(
        request, "evidence.upload",
        f"Uploaded {filename} ({evidence.get_evidence_type_display()}"
        f"{'' if detected or override_type else ', type undetected'}), sha256={digest[:16]}...",
        case=case,
    )

    parse_warning = None
    if etype == EvidenceItem.EvidenceType.OTHER:
        parse_warning = "Couldn't auto-detect the artifact type for this file. Reclassify it manually to parse it."
    else:
        try:
            count = parse_evidence(evidence)
            log_action(request, "evidence.parse", f"Parsed {count} rows from {filename}", case=case)
        except ParseError as exc:
            parse_warning = str(exc)
            log_action(request, "evidence.parse_failed", f"{filename}: {exc}", case=case)

    evidence.refresh_from_db()
    data = EvidenceItemSerializer(evidence).data
    data["status_label"] = "created"
    data["auto_detected"] = detected
    if parse_warning:
        data["parse_warning"] = parse_warning
    return data


class EvidenceUploadAPI(APIView):
    """POST /api/evidence/case/<case_pk>/upload/ (multipart) -- registers
    one or more evidence files, hashes each, auto-detects its artifact type
    (core.parsers.detect) when not explicitly given, and parses it
    immediately. Chromium History uploads also auto-extract that file's
    embedded downloads table (evidence/services.py), so a single "History"
    file surfaces both browsing history and downloads without a second
    upload.

    Accepts multiple files under the repeated `file` field in one request
    (a real drag-a-whole-profile-folder-in batch upload, not N separate
    requests) -- send an entire browser profile's worth of artifact files
    (History, "Login Data", Cookies, places.sqlite, a cache .zip, etc.) at
    once and each gets classified and parsed on its own. A single
    `evidence_type` field, if given, is treated as a manual override applied
    to every file in the batch (used for reclassifying a file whose type
    couldn't be auto-detected) -- normal use just omits it.

    Blocked (per file, as the running count crosses the limit) once the
    org's plan-defined per-case evidence limit is hit; files already
    processed before that point in the batch are kept, not rolled back.

    Stays available regardless of LocalScanAPI's plan/deployment gating --
    this is the universal fallback for any file the local scan can't find,
    can't read, or doesn't apply to (a non-local/remote deployment, an
    export handed to the examiner on removable media, etc.).
    """

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, case_pk):
        case = get_object_or_404(Case, pk=case_pk)
        require_view(request.user, case)
        # Plan check first (402 "upgrade") so a Free-plan owner gets the
        # actionable message instead of a bare role-based 403.
        if is_org_read_only(org_of(request.user)):
            raise PlanLimitExceeded("The Free plan is view-only. Upgrade to upload evidence.")
        require_upload_evidence(request.user, case)

        files = request.FILES.getlist("file")
        if not files:
            raise ValidationError({"file": ["No file(s) provided."]})

        # Optional manual override applied to every file in the batch --
        # normal (auto-detect) use just omits this field entirely.
        override_type = request.data.get("evidence_type") or None
        if override_type and override_type not in EvidenceItem.EvidenceType.values:
            raise ValidationError({"evidence_type": [f"Unknown evidence type '{override_type}'."]})
        note = request.data.get("note", "")

        org = org_of(request.user)
        results = []
        for f in files:
            limit = evidence_limit_status(org, case)
            if not limit["allowed"]:
                results.append({
                    "original_filename": f.name,
                    "status": "blocked",
                    "detail": (
                        f"Your plan allows {limit['limit']} evidence file(s) per case and this case "
                        "is at the limit. Upgrade to add more."
                    ),
                })
                break  # further files would just hit the same wall

            results.append(_ingest_evidence_file(request, case, f.name, f, override_type, note))

        # Single-file requests (the common case from the upload page) get
        # the item back as the sole element of `results` -- still a list,
        # so callers don't need an `if array vs object` branch either way.
        return Response({"results": results}, status=status.HTTP_201_CREATED)


class LocalScanAPI(APIView):
    """POST /api/evidence/case/<case_pk>/scan-local/ -- fully automated
    evidence intake for a desktop/local deployment: scans the machine THIS
    DJANGO PROCESS is running on for installed browser profiles
    (core.browser_detect), and ingests every artifact file found through
    the exact same pipeline as a manual upload (auto-detection, hashing,
    parsing) -- no file picker, no manual step at all for the common case.

    Only makes sense when the examiner's own workstation IS the machine
    running this app (true for the desktop build; see desktop_app.py) --
    on a shared/remote server this would scan the SERVER's disk, not the
    examiner's, so it's gated behind DFS_ENABLE_LOCAL_SCAN (off by
    default) in addition to the org's plan (`feature_local_scan`).

    Anything unreadable (locked by a running browser, permission denied)
    or unrecognized is reported per-file and skipped rather than failing
    the whole scan -- EvidenceUploadAPI's manual multi-file upload stays
    available on the same page as the fallback for exactly those cases.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, case_pk):
        case = get_object_or_404(Case, pk=case_pk)
        require_view(request.user, case)

        if not settings.ENABLE_LOCAL_BROWSER_SCAN:
            raise PermissionDenied(
                "Local machine scanning is disabled on this deployment. Use manual upload instead."
            )

        org = org_of(request.user)
        if is_org_read_only(org):
            raise PlanLimitExceeded("The Free plan is view-only. Upgrade to upload evidence.")
        if not has_feature(org, "feature_local_scan"):
            raise PlanLimitExceeded(
                "Scanning this computer for browser data isn't included on your current plan. "
                "Upgrade to unlock it, or use manual upload below."
            )
        require_upload_evidence(request.user, case)

        include_state = str(request.data.get("include_system_data", "")).lower() in ("1", "true", "yes", "on")
        if include_state and not has_feature(org, "feature_data_recovery"):
            raise PlanLimitExceeded(
                "Collecting browser system data (sessions, bookmarks, preferences) isn't included on your "
                "current plan. Upgrade to unlock it, or scan without that option."
            )

        candidates = []  # list of (display_label, Path)
        for profile in detect_all():
            label = f"{profile.browser} ({profile.profile_name})"
            for kind_label, path in (
                ("History", profile.history_path),
                ("Login Data", profile.logins_path),
                ("Cookies", profile.cookies_path),
            ):
                if path:
                    candidates.append((label, path))
            if include_state:
                for path in profile.state_paths:
                    candidates.append((label, path))

        if not candidates:
            return Response({"results": [], "detail": "No browser profile files were found on this computer."})

        results = []
        for label, path in candidates:
            limit = evidence_limit_status(org, case)
            if not limit["allowed"]:
                results.append({
                    "original_filename": path.name,
                    "status": "blocked",
                    "detail": (
                        f"Your plan allows {limit['limit']} evidence file(s) per case and this case "
                        "is at the limit. Upgrade to add more."
                    ),
                })
                break
            note = f"Auto-detected: {label}"
            results.append(_ingest_evidence_file(request, case, path.name, path, None, note))

        return Response({"results": results}, status=status.HTTP_201_CREATED)


class EvidenceDetailAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, request, pk):
        evidence = get_object_or_404(EvidenceItem.objects.select_related("case", "uploaded_by"), pk=pk)
        require_view(request.user, evidence.case)
        return evidence

    def get(self, request, pk):
        evidence = self.get_object(request, pk)
        return Response(EvidenceItemSerializer(evidence).data)

    def delete(self, request, pk):
        evidence = self.get_object(request, pk)
        require_edit(request.user, evidence.case)
        name = evidence.original_filename
        if evidence.stored_path:
            try:
                Path(evidence.stored_path).unlink(missing_ok=True)
            except Exception:
                pass
        log_action(request, "evidence.delete", f"Deleted evidence {name}", case=evidence.case)
        evidence.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class EvidenceReparseAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        evidence = get_object_or_404(EvidenceItem, pk=pk)
        require_edit(request.user, evidence.case)
        try:
            count = parse_evidence(evidence)
            log_action(request, "evidence.reparse", f"Re-parsed, {count} rows", case=evidence.case)
        except ParseError as exc:
            log_action(request, "evidence.parse_failed", str(exc), case=evidence.case)
            evidence.refresh_from_db()
            return Response(
                {"detail": f"Parsing failed: {exc}", **EvidenceItemSerializer(evidence).data}, status=400
            )
        evidence.refresh_from_db()
        return Response(EvidenceItemSerializer(evidence).data)


class DemoCaseAPI(APIView):
    """POST /api/evidence/demo-case/ -- one-click synthetic demo case,
    still subject to the same read-only / case-limit plan rules."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if request.user.profile.is_viewer_role:
            raise PermissionDenied("Read-only reviewers cannot create cases.")
        org = org_of(request.user)
        if is_org_read_only(org):
            raise PlanLimitExceeded("The Free plan is view-only. Upgrade to create cases.")

        case = Case.objects.create(
            name="Demo Investigation - Sample Browser Artifacts",
            description="Synthetic demo case auto-generated for training / UI walkthrough purposes. "
                         "No real evidence or personal data is involved.",
            investigator=request.user,
            organization=org,
            subject_name="Synthetic Demo Subject",
            tags="demo, training",
            is_demo=True,
        )
        specs = [
            (EvidenceItem.EvidenceType.CHROMIUM_HISTORY, "History"),
            (EvidenceItem.EvidenceType.CHROMIUM_LOGINS, "Login Data"),
            (EvidenceItem.EvidenceType.CHROMIUM_COOKIES, "Cookies"),
            (EvidenceItem.EvidenceType.CHROMIUM_DOWNLOADS, "History"),
            (EvidenceItem.EvidenceType.CACHE_ARCHIVE, "cache_sample.zip"),
        ]
        for etype, fname in specs:
            ev = EvidenceItem.objects.create(
                case=case, evidence_type=etype, original_filename=fname,
                stored_path="", sha256="0" * 64, size_bytes=0,
                uploaded_by=request.user, note="Synthetic demo data",
            )
            load_demo_data(ev)

        log_action(request, "case.demo_created", f"Demo case {case.case_number} created", case=case)
        from cases.serializers import CaseDetailSerializer
        return Response(CaseDetailSerializer(case, context={"request": request}).data, status=201)


class ArtifactTableAPI(APIView):
    """GET /api/evidence/case/<case_pk>/table/<kind>/ -- JSON version of the
    generic artifact table (search/sort/paginate). Export stays a plain
    link to the existing same-origin Django endpoint (session cookie is
    enough for the browser to download the file), which is where the
    per-format plan/feature gate (`feature_csv_export` etc.) is enforced."""

    permission_classes = [permissions.IsAuthenticated]
    pagination_class = ArtifactPagination

    def get(self, request, case_pk, kind):
        if kind not in TABLE_CONFIG:
            raise NotFound("Unknown artifact table.")
        case = get_object_or_404(Case, pk=case_pk)
        require_view(request.user, case)
        cfg = TABLE_CONFIG[kind]

        # Which evidence items actually contributed rows to this table --
        # not "which items were uploaded declaring this type", since a
        # single Chromium History upload now also feeds the Downloads table
        # (see evidence/services.py) and shouldn't be filtered out of it.
        base_qs = cfg["model"].objects.filter(evidence__case=case)
        evidence_qs = case.evidence_items.filter(
            id__in=base_qs.values_list("evidence_id", flat=True).distinct()
        )
        qs = base_qs.select_related("evidence")

        evidence_filter = request.GET.get("evidence", "").strip()
        if evidence_filter:
            qs = qs.filter(evidence_id=evidence_filter)

        q = request.GET.get("q", "").strip()
        if q:
            cond = Q()
            for f in cfg["search_fields"]:
                cond |= Q(**{f"{f}__icontains": q})
            qs = qs.filter(cond)

        sort = request.GET.get("sort", cfg["default_sort"])
        if sort.lstrip("-") not in SORT_WHITELIST:
            sort = cfg["default_sort"]
        qs = qs.order_by(sort, "id")

        org = org_of(request.user)
        file_access = {fmt: has_feature(org, feature) for fmt, feature in EXPORT_FEATURE_MAP.items()}

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        columns = [{"field": f, "label": label} for f, label in cfg["columns"]]
        rows = [
            {col["field"]: _serialize_value(getattr(obj, col["field"])) for col in columns} | {"id": obj.id, "evidence_id": obj.evidence_id}
            for obj in page
        ]
        response = paginator.get_paginated_response(rows)
        response.data["columns"] = columns
        response.data["sort"] = sort
        response.data["q"] = q
        response.data["evidence_filter"] = evidence_filter
        response.data["evidence_options"] = [
            {"id": e.id, "original_filename": e.original_filename} for e in evidence_qs
        ]
        response.data["file_access"] = file_access
        response.data["kind"] = kind
        return response


def _serialize_value(val):
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return val
