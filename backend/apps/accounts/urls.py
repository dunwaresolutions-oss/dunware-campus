from django.urls import path

from .views import CSRFView, LoginView, LogoutView, WhoAmIView

app_name = "accounts"

urlpatterns = [
    path("csrf/", CSRFView.as_view(), name="csrf"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("whoami/", WhoAmIView.as_view(), name="whoami"),
]
