"""Prove the Graph credentials work, without creating a user to do it.

    python manage.py send_test_email you@dash-mfb.com

Reports which stage failed, because the three failure modes need different
fixes: a bad tenant or secret fails at the token step, a missing Mail.Send
permission or an application access policy fails at the send step, and a
console backend means the credentials are simply not configured.
"""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Send a test message through the configured email backend."

    def add_arguments(self, parser):
        parser.add_argument("recipient", help="where to send it")

    def handle(self, *args, **options):
        backend = settings.EMAIL_BACKEND
        self.stdout.write(f"Backend: {backend}")

        if "console" in backend:
            self.stdout.write(
                self.style.WARNING(
                    "\nGraph is not configured, so this will be printed below "
                    "rather than sent.\nSet GRAPH_TENANT_ID, GRAPH_CLIENT_ID, "
                    "GRAPH_CLIENT_SECRET and MS_GRAPH_SENDER in .env to send for real."
                )
            )
        else:
            self.stdout.write(f"Sending as: {settings.MS_GRAPH_SENDER}")
            from loans.mail import GraphError, get_access_token

            try:
                get_access_token(force_refresh=True)
                self.stdout.write(self.style.SUCCESS("Token: acquired"))
            except GraphError as exc:
                raise CommandError(
                    f"Could not get a token: {exc}\n\n"
                    "Check GRAPH_TENANT_ID, GRAPH_CLIENT_ID and "
                    "GRAPH_CLIENT_SECRET. A secret that has expired fails here."
                )

        recipient = options["recipient"]
        message = EmailMultiAlternatives(
            subject=f"{settings.PORTAL_NAME}: test message",
            body=(
                "This is a test from the Loan Reports portal.\n\n"
                "If you received it, password setup and reset emails will "
                "reach people too."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL or None,
            to=[recipient],
        )
        message.attach_alternative(
            '<div style="font-family:-apple-system,Segoe UI,sans-serif">'
            f"<p>This is a test from the <strong>{settings.PORTAL_NAME}</strong> portal.</p>"
            "<p>If you received it, password setup and reset emails will reach "
            "people too.</p></div>",
            "text/html",
        )

        try:
            sent = message.send(fail_silently=False)
        except Exception as exc:
            raise CommandError(
                f"Send failed: {exc}\n\n"
                "A 403 here usually means the app registration is missing the "
                "Mail.Send application permission with admin consent, or an "
                "application access policy excludes this mailbox."
            )

        if sent:
            self.stdout.write(self.style.SUCCESS(f"\nSent to {recipient}."))
        else:
            raise CommandError("The backend reported nothing sent.")
