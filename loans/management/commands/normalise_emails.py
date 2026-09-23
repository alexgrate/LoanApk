"""Lowercase email addresses stored before normalisation was added.

New and edited accounts are normalised by a signal (loans/signals.py), but that
only fires on save - rows written earlier keep whatever case was typed. This
brings them into line.

    python manage.py normalise_emails            # show what would change
    python manage.py normalise_emails --apply    # change it

Collisions are reported rather than merged: if two accounts differ only by the
case of their address, lowercasing both would leave the portal unable to say
which one a reset link belongs to. That needs a person to decide which account
is real.
"""

from collections import defaultdict

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Lowercase user email addresses stored in mixed case."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true", help="write the changes (default: dry run)"
        )

    def handle(self, *args, **options):
        changes = [
            user
            for user in User.objects.exclude(email="")
            if user.email != user.email.strip().lower()
        ]

        # Would any two accounts end up on the same address?
        by_address = defaultdict(list)
        for user in User.objects.exclude(email=""):
            by_address[user.email.strip().lower()].append(user)
        collisions = {
            address: users for address, users in by_address.items() if len(users) > 1
        }

        if collisions:
            self.stdout.write(
                self.style.ERROR("Two accounts share an address once lowercased:\n")
            )
            for address, users in collisions.items():
                names = ", ".join(u.get_username() for u in users)
                self.stdout.write(f"  {address}  ->  {names}")
            self.stdout.write(
                "\nNothing changed. Decide which account is real, change or clear "
                "the other's address, then run this again."
            )
            return

        if not changes:
            self.stdout.write(self.style.SUCCESS("Every address is already lowercase."))
            return

        for user in changes:
            self.stdout.write(
                f"  {user.get_username():<16} {user.email}  ->  {user.email.strip().lower()}"
            )

        if not options["apply"]:
            self.stdout.write(
                f"\n{len(changes)} to change. Re-run with --apply to write."
            )
            return

        for user in changes:
            user.save(update_fields=["email"])  # the signal lowercases it
        self.stdout.write(
            self.style.SUCCESS(f"\nNormalised {len(changes)} address(es).")
        )
