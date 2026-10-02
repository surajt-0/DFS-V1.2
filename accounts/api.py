"""JSON auth + profile API for the React SPA. Session-cookie based, exactly
like the rest of the site: POST /api/accounts/login/ sets Django's session
cookie, and every other API call (billing, cases, evidence...) picks it up
automatically via `credentials: 'include'`.
"""
from django.contrib.auth import authenticate, login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from auditlog.utils import log_action

from .serializers import LoginSerializer, ProfileSerializer, SignupSerializer


class SignupAPI(APIView):
    """POST /api/accounts/signup/ -- creates the user, their own
    single-owner Organization on the Free plan, and logs them in."""

    permission_classes = [permissions.AllowAny]

    @method_decorator(ensure_csrf_cookie)
    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        login(request, user)
        log_action(request, "auth.signup", f"New account created: {user.username}")
        return Response(ProfileSerializer(user.profile).data, status=201)


class LoginAPI(APIView):
    permission_classes = [permissions.AllowAny]

    @method_decorator(ensure_csrf_cookie)
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response({"detail": "Incorrect username or password."}, status=400)
        login(request, user)
        log_action(request, "auth.login", f"{user.username} logged in")
        return Response(ProfileSerializer(user.profile).data)


class LogoutAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        username = request.user.username
        log_action(request, "auth.logout", f"{username} logged out")
        logout(request)
        return Response({"ok": True})


class ProfileAPI(APIView):
    """GET/PATCH /api/accounts/profile/ -- the logged-in user's own profile
    (display name, role label, org name, badge id)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(ProfileSerializer(request.user.profile).data)

    def patch(self, request):
        serializer = ProfileSerializer(request.user.profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class PasswordChangeAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from django.contrib.auth import update_session_auth_hash
        from django.contrib.auth.password_validation import validate_password

        old_password = request.data.get("old_password", "")
        new_password1 = request.data.get("new_password1", "")
        new_password2 = request.data.get("new_password2", "")

        if not request.user.check_password(old_password):
            return Response({"old_password": ["Your current password is incorrect."]}, status=400)
        if new_password1 != new_password2:
            return Response({"new_password2": ["Passwords don't match."]}, status=400)
        try:
            validate_password(new_password1, request.user)
        except Exception as exc:
            return Response({"new_password1": list(exc.messages)}, status=400)

        request.user.set_password(new_password1)
        request.user.save()
        update_session_auth_hash(request, request.user)
        log_action(request, "auth.password_change", "Password changed")
        return Response({"ok": True})
