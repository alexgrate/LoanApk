"""Send mail through the Microsoft Graph API.

Implemented as an ordinary Django email backend, so `PasswordResetForm`,
`send_mail()` and everything else in Django work unchanged - only the transport
differs. Swapping back to SMTP later is a one-line settings change.

App-only authentication (client credentials): the application holds its own
identity in Entra ID and sends as a fixed mailbox. No user is signed in, so
nothing here depends on whose session is active.

Uses `urllib` from the standard library rather than `requests` or `msal`. Two
POST requests do not justify a dependency, and this project has deliberately
stayed pure-Python so the Windows server needs no compiler toolchain.

Required Graph permission: **Mail.Send**, application type, with admin consent.

Note what that grants: `Mail.Send` as an application permission lets this app
send as ANY mailbox in the tenant, not just GRAPH_SENDER. Scope it down with an
application access policy, or the credentials in .env are a tenant-wide
send-as capability:

    New-ApplicationAccessPolicy -AppId <client id> `
      -PolicyScopeGroupId <mail-enabled security group> `
      -AccessRight RestrictAccess `
      -Description "Loan Reports portal may send only as no-reply"
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.cache import cache
from django.core.mail.backends.base import BaseEmailBackend

audit = logging.getLogger("loans.audit")

TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
SEND_URL = "https://graph.microsoft.com/v1.0/users/{sender}/sendMail"
SCOPE = "https://graph.microsoft.com/.default"

TOKEN_CACHE_KEY = "graph-access-token"


class GraphError(Exception):
    """Graph refused a token request or a send."""


def _post(url, data, headers, timeout=20):
    """POST and return the decoded response body, or raise GraphError."""
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise GraphError(f"{exc.code} {exc.reason}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise GraphError(f"could not reach {urllib.parse.urlparse(url).netloc}: {exc.reason}") from exc


def get_access_token(force_refresh=False):
    """An app-only access token, cached until shortly before it expires.

    Without the cache every message would cost a round trip to Entra ID before
    the round trip to Graph, and token endpoints are rate limited.
    """
    if not force_refresh:
        token = cache.get(TOKEN_CACHE_KEY)
        if token:
            return token

    payload = urllib.parse.urlencode(
        {
            "client_id": settings.GRAPH_CLIENT_ID,
            "client_secret": settings.GRAPH_CLIENT_SECRET,
            "scope": SCOPE,
            "grant_type": "client_credentials",
        }
    ).encode()

    data = _post(
        TOKEN_URL.format(tenant=settings.GRAPH_TENANT_ID),
        payload,
        {"Content-Type": "application/x-www-form-urlencoded"},
    )

    token = data.get("access_token")
    if not token:
        raise GraphError("token response contained no access_token")

    # Expire our copy a minute early so a token never goes stale mid-send.
    ttl = max(int(data.get("expires_in", 3600)) - 60, 60)
    cache.set(TOKEN_CACHE_KEY, token, ttl)
    return token


def _as_graph_message(message):
    """Turn a Django EmailMessage into the JSON Graph expects."""
    html = None
    for content, mimetype in getattr(message, "alternatives", []) or []:
        if mimetype == "text/html":
            html = content
            break

    recipients = [
        {"emailAddress": {"address": address}} for address in message.to if address
    ]
    cc = [{"emailAddress": {"address": address}} for address in (message.cc or [])]
    bcc = [{"emailAddress": {"address": address}} for address in (message.bcc or [])]

    return {
        "message": {
            "subject": message.subject,
            "body": {
                "contentType": "HTML" if html else "Text",
                "content": html or message.body,
            },
            "toRecipients": recipients,
            "ccRecipients": cc,
            "bccRecipients": bcc,
        },
        # These are transactional notices, not correspondence anyone needs to
        # read back. Keeping them out of the shared mailbox's Sent Items avoids
        # accumulating thousands of them.
        "saveToSentItems": False,
    }


class GraphEmailBackend(BaseEmailBackend):
    """Django email backend that posts to Graph's sendMail endpoint."""

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        sent = 0
        for message in email_messages:
            if not message.to:
                continue
            try:
                self._send(message)
                sent += 1
            except GraphError as exc:
                audit.error(
                    "MAIL_FAILED to=%s subject=%r error=%s",
                    ",".join(message.to),
                    message.subject,
                    exc,
                )
                if not self.fail_silently:
                    raise
        return sent

    def _send(self, message, retried=False):
        token = get_access_token(force_refresh=retried)
        try:
            _post(
                SEND_URL.format(
                    sender=urllib.parse.quote(settings.GRAPH_SENDER, safe="@.")
                ),
                json.dumps(_as_graph_message(message)).encode("utf-8"),
                {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
        except GraphError as exc:
            # A cached token can be revoked before it expires. One retry with a
            # fresh token distinguishes that from a real failure.
            if not retried and "401" in str(exc):
                cache.delete(TOKEN_CACHE_KEY)
                return self._send(message, retried=True)
            raise

        audit.info(
            "MAIL_SENT to=%s subject=%r", ",".join(message.to), message.subject
        )
