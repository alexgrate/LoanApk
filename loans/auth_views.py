import logging

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render, resolve_url
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme

from . import sso
from .emails import (
    RESET_BODY,
    RESET_SUBJECT,
    client_ip,
    reset_is_throttled,
)

audit = logging.getLogger("loans.audit")


class PortalLoginView(auth_views.LoginView):
    template_name = "registration/login.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(sso_enabled=settings.OIDC_ENABLED, **kwargs)


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "registration/password_reset_form.html"
    email_template_name = RESET_BODY
    html_email_template_name = RESET_BODY
    subject_template_name = RESET_SUBJECT
    success_url = reverse_lazy("password_reset_done")

    def get_extra_email_context(self):
        return {
            "portal_name": settings.PORTAL_NAME,
            "new_account": False,
            "valid_days": settings.PASSWORD_RESET_TIMEOUT // 86400,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extra_email_context = self.get_extra_email_context()

    def post(self, request, *args, **kwargs):
        if reset_is_throttled(request):
            return render(
                request,
                "registration/password_reset_throttled.html",
                {"portal_name": settings.PORTAL_NAME},
                status=429,
            )
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        audit.info(
            "PASSWORD_RESET_REQUESTED email=%s ip=%s",
            form.cleaned_data.get("email", "?"),
            client_ip(self.request),
        )
        return super().form_valid(form)


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "registration/password_reset_done.html"


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "registration/password_reset_confirm.html"
    success_url = reverse_lazy("password_reset_complete")

    def form_valid(self, form):
        response = super().form_valid(form)
        audit.info(
            "PASSWORD_SET user=%s ip=%s",
            self.user.get_username(),
            client_ip(self.request),
        )
        return response


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "registration/password_reset_complete.html"


def _safe_next(request, candidate):
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return resolve_url(settings.LOGIN_REDIRECT_URL)


def sso_login(request):
    if not settings.OIDC_ENABLED:
        raise Http404("single sign-on is not configured")

    try:
        destination = sso.begin(request, request.GET.get("next", ""))
    except sso.SSOError as exc:
        audit.error("SSO_UNAVAILABLE error=%s ip=%s", exc, client_ip(request))
        return render(
            request,
            "registration/sso_error.html",
            {"reason": "Oracle could not be reached.", "portal_name": settings.PORTAL_NAME},
            status=503,
        )
    return HttpResponseRedirect(destination)


def sso_callback(request):
    if not settings.OIDC_ENABLED:
        raise Http404("single sign-on is not configured")

    refusal = request.GET.get("error")
    if refusal:
        audit.warning(
            "SSO_REFUSED error=%s ip=%s", refusal, client_ip(request)
        )
        request.session.pop(sso.STATE_KEY, None)
        request.session.pop(sso.VERIFIER_KEY, None)
        return render(
            request,
            "registration/sso_error.html",
            {
                "reason": (
                    "Your account is not assigned to this application."
                    if refusal == "access_denied"
                    else "Oracle refused the sign-in."
                ),
                "portal_name": settings.PORTAL_NAME,
            },
            status=403,
        )

    try:
        person = sso.finish(
            request, request.GET.get("code"), request.GET.get("state")
        )
    except sso.SSOError as exc:
        audit.warning("SSO_FAILED error=%s ip=%s", exc, client_ip(request))
        return render(
            request,
            "registration/sso_error.html",
            {
                "reason": "The sign-in could not be completed.",
                "portal_name": settings.PORTAL_NAME,
            },
            status=400,
        )

    user = sso.user_for(person)
    if not user.is_active:
        audit.warning("SSO_INACTIVE user=%s ip=%s", user.get_username(), client_ip(request))
        return render(
            request,
            "registration/sso_error.html",
            {
                "reason": "This account has been suspended in the portal.",
                "portal_name": settings.PORTAL_NAME,
            },
            status=403,
        )

    destination = _safe_next(request, request.session.pop(sso.NEXT_KEY, ""))

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    audit.info(
        "SSO_SIGNED_IN user=%s email=%s ip=%s",
        user.get_username(),
        user.email,
        client_ip(request),
    )

    return HttpResponseRedirect(destination)
