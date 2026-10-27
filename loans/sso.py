import base64
import hashlib
import json
import logging
import secrets
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.contrib.auth.models import User

audit = logging.getLogger("loans.audit")

DISCOVERY_PATH = "/.well-known/openid-configuration"

SCOPES = "openid profile email"

STATE_KEY = "sso_state"
VERIFIER_KEY = "sso_verifier"
NEXT_KEY = "sso_next"

_discovery_cache = {}


class SSOError(Exception):
    pass


def _request(url, data=None, headers=None, timeout=20):
    request = urllib.request.Request(
        url, data=data, headers=headers or {}, method="POST" if data else "GET"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise SSOError(f"{exc.code} {exc.reason}: {detail}") from exc
    except urllib.error.URLError as exc:
        host = urllib.parse.urlparse(url).netloc
        raise SSOError(f"could not reach {host}: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise SSOError(f"{urllib.parse.urlparse(url).path} returned no JSON") from exc


def discover():
    issuer = settings.OIDC_ISSUER
    if issuer in _discovery_cache:
        return _discovery_cache[issuer]

    data = _request(issuer + DISCOVERY_PATH)
    try:
        endpoints = {
            "authorize": data["authorization_endpoint"],
            "token": data["token_endpoint"],
            "userinfo": data["userinfo_endpoint"],
            "logout": data.get("end_session_endpoint", ""),
        }
    except KeyError as exc:
        raise SSOError(f"discovery document has no {exc.args[0]}") from exc

    _discovery_cache[issuer] = endpoints
    return endpoints


def begin(request, next_url=""):
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )

    request.session[STATE_KEY] = state
    request.session[VERIFIER_KEY] = verifier
    request.session[NEXT_KEY] = next_url

    query = urllib.parse.urlencode(
        {
            "client_id": settings.OIDC_CLIENT_ID,
            "redirect_uri": settings.OIDC_REDIRECT_URI,
            "response_type": "code",
            "scope": SCOPES,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{discover()['authorize']}?{query}"


def finish(request, code, state):
    expected = request.session.pop(STATE_KEY, None)
    verifier = request.session.pop(VERIFIER_KEY, None)

    if not expected or not verifier:
        raise SSOError("no sign-in was started from this browser")
    if not state or not secrets.compare_digest(state, expected):
        raise SSOError("state did not match the one we issued")
    if not code:
        raise SSOError("Oracle returned no authorization code")

    return _profile(_exchange(code, verifier))


def _exchange(code, verifier):
    credentials = f"{settings.OIDC_CLIENT_ID}:{settings.OIDC_CLIENT_SECRET}"
    basic = base64.b64encode(credentials.encode()).decode()

    data = _request(
        discover()["token"],
        urllib.parse.urlencode(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.OIDC_REDIRECT_URI,
                "code_verifier": verifier,
            }
        ).encode(),
        {
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )

    token = data.get("access_token")
    if not token:
        raise SSOError("token response contained no access_token")
    return token


def _profile(access_token):
    data = _request(
        discover()["userinfo"], headers={"Authorization": f"Bearer {access_token}"}
    )

    email = (
        data.get("email")
        or data.get("preferred_username")
        or data.get("sub")
        or ""
    ).strip().lower()

    if "@" not in email:
        raise SSOError("Oracle returned no email address for this account")

    return {
        "email": email,
        "first_name": (data.get("given_name") or "").strip(),
        "last_name": (data.get("family_name") or "").strip(),
    }


def _username_for(email):
    local = email.split("@")[0][:150]
    if local and not User.objects.filter(username=local).exclude(email=email).exists():
        return local
    return email[:150]


def user_for(person):
    email = person["email"]
    user = User.objects.filter(email=email).first()
    created = user is None

    if created:
        user = User(username=_username_for(email), email=email)
        user.set_unusable_password()

    user.first_name = person["first_name"][:150]
    user.last_name = person["last_name"][:150]

    is_admin = email in settings.OIDC_ADMIN_EMAILS
    user.is_staff = is_admin
    user.is_superuser = is_admin

    if created:
        user.is_active = True

    user.save()

    audit.info(
        "SSO_ACCOUNT %s user=%s email=%s admin=%s",
        "created" if created else "updated",
        user.get_username(),
        email,
        is_admin,
    )
    return user
