from django.urls import path

from .views import (
    CSRFView,
    InviteAcceptView,
    LoginView,
    LogoutView,
    MFAConfirmView,
    MFASetupView,
    MFAStatusView,
    StaffInviteView,
    UsersView,
    WhoAmIView,
)

app_name = "accounts"

urlpatterns = [
    path("csrf/", CSRFView.as_view(), name="csrf"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("whoami/", WhoAmIView.as_view(), name="whoami"),
    path("mfa/setup/", MFASetupView.as_view(), name="mfa-setup"),
    path("mfa/confirm/", MFAConfirmView.as_view(), name="mfa-confirm"),
    path("mfa/status/", MFAStatusView.as_view(), name="mfa-status"),
    path("users/", UsersView.as_view(), name="users"),
    path("invite/", StaffInviteView.as_view(), name="invite-create"),
    path("invite/accept/", InviteAcceptView.as_view(), name="invite-accept"),
]
