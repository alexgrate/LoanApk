"""The forgotten-password flow.

Django's own password reset views, with three additions:

* a per-address throttle, because django-axes guards the login form and not
  this one, and an unthrottled reset form is a way to make the portal send
  mail to any address an attacker names;
* audit logging of requests and completions, matching how exports and document
  access are already recorded;
* this portal's templates and wording.

Deliberately unchanged: the form always reports success, whether or not the
address belongs to an account. Saying "no such user" would turn the page into a
way to find out who has a login.
"""

import logging

from django.conf import settings
from django.contrib.auth import views as auth_views
from django.shortcuts import render
from django.urls import reverse_lazy

from .emails import (
    RESET_BODY,
    RESET_SUBJECT,
    client_ip,
    reset_is_throttled,
)

audit = logging.getLogger("loans.audit")


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
        # Logged whether or not an account matched: the interesting signal is
        # somebody asking, and matching would leak which addresses exist.
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
