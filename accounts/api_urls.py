from django.urls import path

from . import api

app_name = "accounts_api"

urlpatterns = [
    path("signup/", api.SignupAPI.as_view(), name="signup"),
    path("login/", api.LoginAPI.as_view(), name="login"),
    path("logout/", api.LogoutAPI.as_view(), name="logout"),
    path("profile/", api.ProfileAPI.as_view(), name="profile"),
    path("password-change/", api.PasswordChangeAPI.as_view(), name="password_change"),
]
