"""Password setup and reset.

This is the one unauthenticated flow in the portal that can end with somebody
signed in, so it gets tested as carefully as document access: that links work
once, that they expire, that the form does not reveal which addresses have
accounts, and that it cannot be used to send unlimited mail.
"""

import re

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from loans.emails import set_unguessable_password

LINK = re.compile(r"/password-reset/(?P<uid>[^/]+)/(?P<token>[^/\"\s]+)/")


def link_in(message):
    """The reset URL out of a sent message, HTML part or plain."""
    bodies = [message.body] + [content for content, _type in message.alternatives]
    for body in bodies:
        found = LINK.search(body)
        if found:
            return found.group(0)
    raise AssertionError("no password-reset link in the message")


class SignInMixin:
    def sign_in(self, username, password):
        """Sign in through the real form.

        `client.login()` calls authenticate() with no request, which
        AxesBackend refuses - and going through the form tests the path people
        actually use.
        """
        response = self.client.post(
            reverse("login"), {"username": username, "password": password}
        )
        return response.status_code == 302


class PasswordResetFlowTests(SignInMixin, TestCase):
    databases = {"default"}

    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        self.user = User.objects.create_user(
            "clerk", email="clerk@example.invalid", password="old-password-9914"
        )

    def test_request_page_renders_and_is_public(self):
        response = self.client.get(reverse("password_reset"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reset your password")

    def test_sign_in_page_links_to_it(self):
        self.assertContains(self.client.get(reverse("login")), reverse("password_reset"))

    def test_known_address_receives_a_link(self):
        self.client.post(reverse("password_reset"), {"email": "clerk@example.invalid"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("reset your password", mail.outbox[0].subject.lower())
        self.assertIn("clerk@example.invalid", mail.outbox[0].to)

    def test_unknown_address_looks_identical_and_sends_nothing(self):
        """The page must not reveal who has an account."""
        known = self.client.post(
            reverse("password_reset"), {"email": "clerk@example.invalid"}, follow=True
        )
        cache.clear()
        unknown = self.client.post(
            reverse("password_reset"), {"email": "nobody@example.invalid"}, follow=True
        )
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.redirect_chain, unknown.redirect_chain)
        self.assertEqual(len(mail.outbox), 1)  # only the real one

    def test_the_link_sets_a_password_and_signs_in(self):
        self.client.post(reverse("password_reset"), {"email": "clerk@example.invalid"})
        # Django's confirm view redirects to a set-password URL first.
        response = self.client.get(link_in(mail.outbox[0]), follow=True)
        self.assertContains(response, "Choose a password")

        self.client.post(
            response.redirect_chain[-1][0] if response.redirect_chain else link_in(mail.outbox[0]),
            {"new_password1": "Sable-Harbour-71", "new_password2": "Sable-Harbour-71"},
            follow=True,
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Sable-Harbour-71"))
        self.assertTrue(self.sign_in("clerk", "Sable-Harbour-71"))

    def test_a_link_cannot_be_used_twice(self):
        self.client.post(reverse("password_reset"), {"email": "clerk@example.invalid"})
        url = link_in(mail.outbox[0])
        first = self.client.get(url, follow=True)
        self.client.post(
            first.redirect_chain[-1][0],
            {"new_password1": "Sable-Harbour-71", "new_password2": "Sable-Harbour-71"},
            follow=True,
        )
        # Same link again: the token is spent.
        self.assertContains(self.client.get(url, follow=True), "expired")

    def test_old_password_stops_working(self):
        self.client.post(reverse("password_reset"), {"email": "clerk@example.invalid"})
        response = self.client.get(link_in(mail.outbox[0]), follow=True)
        self.client.post(
            response.redirect_chain[-1][0],
            {"new_password1": "Sable-Harbour-71", "new_password2": "Sable-Harbour-71"},
            follow=True,
        )
        self.assertFalse(self.sign_in("clerk", "old-password-9914"))

    @override_settings(PASSWORD_RESET_MAX_PER_HOUR=3)
    def test_requests_are_throttled(self):
        """django-axes guards the login form, not this one."""
        for _ in range(3):
            response = self.client.post(
                reverse("password_reset"), {"email": "clerk@example.invalid"}
            )
            self.assertEqual(response.status_code, 302)

        blocked = self.client.post(
            reverse("password_reset"), {"email": "clerk@example.invalid"}
        )
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(len(mail.outbox), 3, "a throttled request still sent mail")

    def test_inactive_accounts_get_nothing(self):
        self.user.is_active = False
        self.user.save()
        self.client.post(reverse("password_reset"), {"email": "clerk@example.invalid"})
        self.assertEqual(len(mail.outbox), 0)


class UnguessablePasswordTests(TestCase):
    databases = {"default"}

    def test_new_accounts_are_reachable_by_the_reset_flow(self):
        """The reason set_unusable_password() is not used.

        `PasswordResetForm` silently skips users whose password is unusable, so
        an account created that way would never receive its own setup link.
        """
        user = User(username="newcomer", email="newcomer@example.invalid")
        set_unguessable_password(user)
        user.save()
        self.assertTrue(user.has_usable_password())

        mail.outbox.clear()
        cache.clear()
        self.client.post(reverse("password_reset"), {"email": "newcomer@example.invalid"})
        self.assertEqual(len(mail.outbox), 1)

    def test_the_generated_password_is_long_and_random(self):
        a, b = User(username="a"), User(username="b")
        set_unguessable_password(a)
        set_unguessable_password(b)
        self.assertNotEqual(a.password, b.password)


class AdminUserCreationTests(TestCase):
    databases = {"default"}

    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        self.admin = User.objects.create_superuser(
            "boss", email="boss@example.invalid", password="admin-password-4417"
        )
        self.client.force_login(self.admin)

    def test_the_add_form_asks_for_no_password(self):
        response = self.client.get(reverse("admin:auth_user_add"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="password1"')
        self.assertContains(response, 'name="email"')

    def test_creating_a_user_emails_a_setup_link(self):
        self.client.post(
            reverse("admin:auth_user_add"),
            {
                "username": "newcomer",
                "email": "newcomer@example.invalid",
                "first_name": "New",
                "last_name": "Comer",
            },
        )
        user = User.objects.get(username="newcomer")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("set your password", mail.outbox[0].subject.lower())
        self.assertIn("newcomer@example.invalid", mail.outbox[0].to)

        # And that link genuinely works.
        response = self.client.logout() or self.client.get(
            link_in(mail.outbox[0]), follow=True
        )
        self.client.post(
            response.redirect_chain[-1][0],
            {"new_password1": "Thistle-Wagon-88", "new_password2": "Thistle-Wagon-88"},
            follow=True,
        )
        user.refresh_from_db()
        self.assertTrue(user.check_password("Thistle-Wagon-88"))

    def test_email_is_required(self):
        self.client.post(
            reverse("admin:auth_user_add"), {"username": "noemail", "email": ""}
        )
        self.assertFalse(User.objects.filter(username="noemail").exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_duplicate_emails_are_refused(self):
        """Two accounts on one address makes the reset flow ambiguous."""
        self.client.post(
            reverse("admin:auth_user_add"),
            {"username": "second", "email": "BOSS@example.invalid"},
        )
        self.assertFalse(User.objects.filter(username="second").exists())

    def test_the_button_resends_the_link(self):
        user = User.objects.create_user(
            "clerk", email="clerk@example.invalid", password="x"
        )
        mail.outbox.clear()
        response = self.client.get(
            reverse("admin:auth_user_send_setup_email", args=[user.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)

    def test_the_button_is_only_reachable_by_staff(self):
        user = User.objects.create_user("clerk", email="clerk@example.invalid", password="x")
        self.client.logout()
        response = self.client.get(
            reverse("admin:auth_user_send_setup_email", args=[user.pk])
        )
        self.assertNotEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_the_bulk_action_sends_to_each_selected_user(self):
        for name in ("one", "two"):
            User.objects.create_user(name, email=f"{name}@example.invalid", password="x")
        mail.outbox.clear()
        self.client.post(
            reverse("admin:auth_user_changelist"),
            {
                "action": "send_setup_email",
                "_selected_action": [
                    str(u.pk) for u in User.objects.filter(username__in=["one", "two"])
                ],
            },
        )
        self.assertEqual(len(mail.outbox), 2)


class EmailCaseTests(TestCase):
    """Dominion@ and dominion@ must be one address, everywhere."""

    databases = {"default"}

    def setUp(self):
        cache.clear()
        mail.outbox.clear()

    def test_stored_lowercase_whatever_was_typed(self):
        user = User.objects.create_user(
            "casey", email="  Dominion@Dash-MFB.COM  ", password="x"
        )
        self.assertEqual(user.email, "dominion@dash-mfb.com")

    def test_normalisation_survives_an_edit(self):
        user = User.objects.create_user("casey", email="a@example.invalid", password="x")
        user.email = "Dominion@DASH-MFB.com"
        user.save()
        user.refresh_from_db()
        self.assertEqual(user.email, "dominion@dash-mfb.com")

    def test_reset_finds_the_account_whatever_case_is_typed(self):
        User.objects.create_user("casey", email="dominion@dash-mfb.com", password="x")
        for typed in (
            "dominion@dash-mfb.com",
            "Dominion@dash-mfb.com",
            "DOMINION@DASH-MFB.COM",
        ):
            mail.outbox.clear()
            cache.clear()
            self.client.post(reverse("password_reset"), {"email": typed})
            self.assertEqual(len(mail.outbox), 1, f"no link sent for {typed!r}")

    def test_exact_lookups_work_now(self):
        """The reason for normalising, not just matching case-insensitively."""
        User.objects.create_user("casey", email="Dominion@Dash-MFB.com", password="x")
        self.assertTrue(User.objects.filter(email="dominion@dash-mfb.com").exists())


class AdminEmailCaseTests(TestCase):
    databases = {"default"}

    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        self.admin = User.objects.create_superuser(
            "boss", email="boss@example.invalid", password="admin-password-4417"
        )
        self.client.force_login(self.admin)

    def test_a_different_case_counts_as_a_duplicate(self):
        User.objects.create_user("first", email="dominion@dash-mfb.com", password="x")
        self.client.post(
            reverse("admin:auth_user_add"),
            {"username": "second", "email": "Dominion@Dash-MFB.COM"},
        )
        self.assertFalse(
            User.objects.filter(username="second").exists(),
            "a second account was created on the same address in different case",
        )

    def test_created_users_are_stored_lowercase(self):
        self.client.post(
            reverse("admin:auth_user_add"),
            {"username": "newcomer", "email": "Dominion@Dash-MFB.COM"},
        )
        user = User.objects.get(username="newcomer")
        self.assertEqual(user.email, "dominion@dash-mfb.com")
        self.assertIn("dominion@dash-mfb.com", mail.outbox[0].to)
