from django.contrib import admin
from django.contrib.auth import views as django_auth_views
from django.http import HttpResponse
from django.urls import include, path

from loans import auth_views


def robots_txt(request):
    """Disallow every crawler across the whole site."""
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")


urlpatterns = [
    path("robots.txt", robots_txt),
    path("admin/", admin.site.urls),
    path(
        "login/",
        django_auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("logout/", django_auth_views.LogoutView.as_view(), name="logout"),

    # Forgotten password. Four steps, all public by necessity: ask, confirm
    # sent, choose a new password from the emailed link, done.
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
