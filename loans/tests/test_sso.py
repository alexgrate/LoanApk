import urllib.parse

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from loans import sso

ISSUER = "https://idcs-test.identity.oraclecloud.com"
REDIRECT = "http://testserver/sso/callback/"

ENDPOINTS = {
    "authorize": f"{ISSUER}/oauth2/v1/authorize",
    "token": f"{ISSUER}/oauth2/v1/token",
    "userinfo": f"{ISSUER}/oauth2/v1/userinfo",
    "logout": f"{ISSUER}/oauth2/v1/userlogout",
}

SSO_SETTINGS = {
    "OIDC_ENABLED": True,
    "OIDC_ISSUER": ISSUER,
    "OIDC_CLIENT_ID": "test-client",
    "OIDC_CLIENT_SECRET": "test-secret",
    "OIDC_REDIRECT_URI": REDIRECT,
    "OIDC_ADMIN_EMAILS": [],
}


class FakeOracle:
    def __init__(self, claims=None, token_error=None):
        self.claims = claims or {
            "sub": "1a2b3c",
            "email": "Chinyere.Okeke@Dash-MFB.com",
            "given_name": "Chinyere",
            "family_name": "Okeke",
        }
        self.token_error = token_error
        self.token_request = None

    def __call__(self, url, data=None, headers=None, timeout=20):
        if url.endswith(sso.DISCOVERY_PATH):
            return {
                "authorization_endpoint": ENDPOINTS["authorize"],
                "token_endpoint": ENDPOINTS["token"],
                "userinfo_endpoint": ENDPOINTS["userinfo"],
                "end_session_endpoint": ENDPOINTS["logout"],
            }
        if url == ENDPOINTS["token"]:
            if self.token_error:
                raise sso.SSOError(self.token_error)
            self.token_request = dict(
                urllib.parse.parse_qsl(data.decode()) if data else {}
            )
            return {"access_token": "an-access-token", "token_type": "Bearer"}
        if url == ENDPOINTS["userinfo"]:
            return self.claims
        raise AssertionError(f"unexpected request to {url}")


@override_settings(**SSO_SETTINGS)
class SSOTestCase(TestCase):
    databases = {"default"}

    def setUp(self):
        self.oracle = FakeOracle()
        self._real_request = sso._request
        sso._request = self.oracle
        sso._discovery_cache.clear()
        self.addCleanup(self._restore)

    def _restore(self):
        sso._request = self._real_request
        sso._discovery_cache.clear()

    def start(self, next_url=""):
        url = reverse("sso_login")
        if next_url:
            url += "?next=" + urllib.parse.quote(next_url)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        query = urllib.parse.parse_qs(
            urllib.parse.urlparse(response["Location"]).query
        )
        return query["state"][0]

    def callback(self, state, code="an-auth-code"):
        return self.client.get(
            reverse("sso_callback"), {"code": code, "state": state}
        )


class StartingTests(SSOTestCase):
    def test_the_redirect_carries_what_oracle_needs(self):
        response = self.client.get(reverse("sso_login"))
        location = urllib.parse.urlparse(response["Location"])
        query = urllib.parse.parse_qs(location.query)

        self.assertTrue(response["Location"].startswith(ENDPOINTS["authorize"]))
        self.assertEqual(query["client_id"], ["test-client"])
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["redirect_uri"], [REDIRECT])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertIn("openid", query["scope"][0])

    def test_pkce_sends_a_challenge_not_the_verifier(self):
        response = self.client.get(reverse("sso_login"))
        query = urllib.parse.parse_qs(urllib.parse.urlparse(response["Location"]).query)
        self.assertNotEqual(
            query["code_challenge"][0], self.client.session[sso.VERIFIER_KEY]
        )

    def test_every_attempt_gets_a_fresh_state(self):
        self.assertNotEqual(self.start(), self.start())

    @override_settings(OIDC_ISSUER="https://idcs-abc....identity.oraclecloud.com")
    def test_a_malformed_issuer_shows_a_page_not_a_crash(self):
        sso._request = self._real_request
        response = self.client.get(reverse("sso_login"))
        self.assertEqual(response.status_code, 503)


class ReturningTests(SSOTestCase):
    def test_a_valid_return_creates_the_account_and_signs_in(self):
        response = self.callback(self.start())
        self.assertEqual(response.status_code, 302)

        user = User.objects.get(email="chinyere.okeke@dash-mfb.com")
        self.assertEqual(user.first_name, "Chinyere")
        self.assertEqual(user.last_name, "Okeke")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_the_email_is_stored_lowercase(self):
        self.callback(self.start())
        self.assertTrue(
            User.objects.filter(email="chinyere.okeke@dash-mfb.com").exists()
        )

    def test_the_code_is_redeemed_with_the_verifier(self):
        state = self.start()
        verifier = self.client.session[sso.VERIFIER_KEY]
        self.callback(state)
        self.assertEqual(self.oracle.token_request["code_verifier"], verifier)
        self.assertEqual(self.oracle.token_request["grant_type"], "authorization_code")

    def test_signing_in_again_does_not_make_a_second_account(self):
        self.callback(self.start())
        self.client.logout()
        self.callback(self.start())
        self.assertEqual(User.objects.filter(email__contains="chinyere").count(), 1)

    def test_a_changed_name_is_picked_up(self):
        self.callback(self.start())
        self.client.logout()
        self.oracle.claims = dict(self.oracle.claims, family_name="Nwosu")
        self.callback(self.start())
        self.assertEqual(
            User.objects.get(email="chinyere.okeke@dash-mfb.com").last_name, "Nwosu"
        )

    def test_the_account_cannot_be_signed_into_with_a_password(self):
        self.callback(self.start())
        user = User.objects.get(email="chinyere.okeke@dash-mfb.com")
        self.assertFalse(user.has_usable_password())


class RefusalTests(SSOTestCase):
    def test_a_forged_state_is_refused(self):
        self.start()
        response = self.callback("not-the-state-we-issued")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(User.objects.count(), 0)

    def test_a_callback_with_no_sign_in_started_is_refused(self):
        response = self.callback("anything")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(User.objects.count(), 0)

    def test_a_state_cannot_be_replayed(self):
        state = self.start()
        self.callback(state)
        self.client.logout()
        self.assertEqual(self.callback(state).status_code, 400)

    def test_oracle_refusing_the_person_says_so(self):
        self.start()
        response = self.client.get(
            reverse("sso_callback"), {"error": "access_denied"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "not assigned", status_code=403)
        self.assertEqual(User.objects.count(), 0)

    def test_a_failed_exchange_creates_nobody(self):
        state = self.start()
        self.oracle.token_error = "400 Bad Request: invalid_grant"
        self.assertEqual(self.callback(state).status_code, 400)
        self.assertEqual(User.objects.count(), 0)

    def test_an_account_with_no_email_is_refused(self):
        state = self.start()
        self.oracle.claims = {"sub": "1a2b3c", "given_name": "Nameless"}
        self.assertEqual(self.callback(state).status_code, 400)
        self.assertEqual(User.objects.count(), 0)

    def test_a_suspended_account_stays_out(self):
        self.callback(self.start())
        self.client.logout()
        User.objects.filter(email__contains="chinyere").update(is_active=False)

        response = self.callback(self.start())
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("_auth_user_id", self.client.session)


class AdminTests(SSOTestCase):
    @override_settings(OIDC_ADMIN_EMAILS=["chinyere.okeke@dash-mfb.com"])
    def test_a_listed_address_gets_admin(self):
        self.callback(self.start())
        user = User.objects.get(email="chinyere.okeke@dash-mfb.com")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_an_unlisted_address_does_not(self):
        self.callback(self.start())
        user = User.objects.get(email="chinyere.okeke@dash-mfb.com")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_admin_is_withdrawn_when_the_address_is_removed(self):
        with override_settings(OIDC_ADMIN_EMAILS=["chinyere.okeke@dash-mfb.com"]):
            self.callback(self.start())
            self.client.logout()

        self.callback(self.start())
        self.assertFalse(
            User.objects.get(email="chinyere.okeke@dash-mfb.com").is_staff
        )


class NextUrlTests(SSOTestCase):
    def test_a_local_destination_is_honoured(self):
        response = self.callback(self.start(next_url="/cashback/"))
        self.assertEqual(response["Location"], "/cashback/")

    def test_an_offsite_destination_is_refused(self):
        response = self.callback(self.start(next_url="https://evil.invalid/steal"))
        self.assertNotIn("evil.invalid", response["Location"])

    def test_the_default_is_the_dashboard(self):
        response = self.callback(self.start())
        self.assertEqual(response["Location"], reverse("dashboard"))


class SwitchedOffTests(TestCase):
    databases = {"default"}

    @override_settings(OIDC_ENABLED=False)
    def test_the_routes_are_gone(self):
        self.assertEqual(self.client.get(reverse("sso_login")).status_code, 404)
        self.assertEqual(self.client.get(reverse("sso_callback")).status_code, 404)

    @override_settings(OIDC_ENABLED=False)
    def test_the_sign_in_page_offers_only_a_password(self):
        response = self.client.get(reverse("login"))
        self.assertNotContains(response, reverse("sso_login"))
        self.assertContains(response, 'name="password"')

    @override_settings(**SSO_SETTINGS)
    def test_the_button_replaces_the_password_form_when_configured(self):
        response = self.client.get(reverse("login"))
        self.assertContains(response, reverse("sso_login"))
        self.assertNotContains(response, 'name="password"')
