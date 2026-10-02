"""
Lightweight, low-noise audit middleware. We deliberately do NOT log every
GET request (that would drown the trail in noise) -- state-changing actions
(uploads, parses, exports, case edits) call `log_action` explicitly from
their views instead. This middleware only records authentication events
that Django's own signals make easy to hook centrally.
"""
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .utils import log_action


class AuditLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)


@receiver(user_logged_in)
def _on_login(sender, request, user, **kwargs):
    log_action(request, "auth.login", f"{user.get_username()} logged in")


@receiver(user_logged_out)
def _on_logout(sender, request, user, **kwargs):
    if user:
        log_action(request, "auth.logout", f"{user.get_username()} logged out")


@receiver(user_login_failed)
def _on_login_failed(sender, credentials, request=None, **kwargs):
    if request is not None:
        log_action(request, "auth.login_failed", f"Failed login for '{credentials.get('username', '?')}'")
