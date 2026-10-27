from django.contrib import admin
from django.contrib.auth import views as django_auth_views
from django.http import HttpResponse
from django.urls import include, path

from loans import auth_views


def robots_txt(request):
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")


urlpatterns = [
    path("robots.txt", robots_txt),
    path("admin/", admin.site.urls),
    path(
        "login/",
        auth_views.PortalLoginView.as_view(),
        name="login",
    ),
    path("logout/", django_auth_views.LogoutView.as_view(), name="logout"),

    path("sso/login/", auth_views.sso_login, name="sso_login"),
    path("sso/callback/", auth_views.sso_callback, name="sso_callback"),

    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "password-reset/sent/",
        auth_views.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "password-reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    path("", include("loans.urls")),
]
