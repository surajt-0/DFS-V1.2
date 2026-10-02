from __future__ import annotations


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_action(request, action: str, detail: str = "", case=None):
    """Fire-and-forget audit trail write. Never raises into the caller --
    a broken audit write must not block the examiner's actual work, but it
    is logged to the console so an admin will still notice."""
    from .models import AuditLogEntry
    try:
        user = getattr(request, "user", None)
        AuditLogEntry.objects.create(
            user=user if (user and user.is_authenticated) else None,
            username_snapshot=(user.get_username() if (user and user.is_authenticated) else "anonymous"),
            action=action,
            detail=detail,
            case=case,
            ip_address=_client_ip(request),
            path=request.path[:300],
        )
    except Exception as exc:  # pragma: no cover - defensive
        import logging
        logging.getLogger("auditlog").warning("Failed to write audit entry: %s", exc)
