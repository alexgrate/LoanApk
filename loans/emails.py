import logging

from django.conf import settings
from django.contrib.auth.forms import PasswordResetForm
from django.core.cache import cache
from django.utils.crypto import get_random_string

audit = logging.getLogger("loans.audit")

SETUP_SUBJECT = "registration/account_setup_subject.txt"
SETUP_BODY = "registration/account_setup_email.html"
RESET_SUBJECT = "registration/password_reset_subject.txt"
RESET_BODY = "registration/password_reset_email.html"

THROTTLE_PREFIX = "pwreset-throttle:"


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def reset_is_throttled(request):
    limit = settings.PASSWORD_RESET_MAX_PER_HOUR
    if limit <= 0:
        return False

    key = THROTTLE_PREFIX + client_ip(request)
    count = cache.get(key, 0)
    if count >= limit:
        audit.warning(
            "PASSWORD_RESET_THROTTLED ip=%s attempts=%s", client_ip(request), count
        )
        return True

    if count:
        cache.incr(key)
    else:
        cache.set(key, 1, 3600)
    return False


def set_unguessable_password(user):
    user.set_password(get_random_string(64))
    return user


def send_setup_link(user, request, new_account=False):
    if not user.email:
        audit.warning(
            "PASSWORD_LINK_SKIPPED user=%s reason=no-email", user.get_username()
        )
        return False
    if not user.is_active:
        audit.warning(
            "PASSWORD_LINK_SKIPPED user=%s reason=inactive", user.get_username()
        )
        return False

    form = PasswordResetForm({"email": user.email})
    if not form.is_valid():
        audit.warning(
            "PASSWORD_LINK_SKIPPED user=%s reason=invalid-email", user.get_username()
        )
        return False

    form.save(
        request=request,
        use_https=request.is_secure(),
        from_email=settings.DEFAULT_FROM_EMAIL or None,
        subject_template_name=SETUP_SUBJECT if new_account else RESET_SUBJECT,
        email_template_name=SETUP_BODY if new_account else RESET_BODY,
        html_email_template_name=SETUP_BODY if new_account else RESET_BODY,
        extra_email_context={
            "portal_name": settings.PORTAL_NAME,
            "new_account": new_account,
            "valid_days": settings.PASSWORD_RESET_TIMEOUT // 86400,
        },
    )

    audit.info(
        "PASSWORD_LINK_SENT user=%s email=%s kind=%s by=%s ip=%s",
        user.get_username(),
        user.email,
        "setup" if new_account else "reset",
        getattr(request.user, "username", "-") or "-",
        client_ip(request),
    )
    return True
