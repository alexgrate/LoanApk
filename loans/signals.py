"""Keep user email addresses in one canonical form.

Django's reset flow already matches case-insensitively, so `Dominion@` and
`dominion@` find the same account. What it does not do is normalise what gets
stored, which leaves two problems:

* an exact lookup - `User.objects.get(email=...)` - silently misses a row whose
  stored case differs, and that failure looks like "no such user" rather than
  like a bug;
* two accounts can end up on what is really one address if they were created
  outside the admin, via createsuperuser or the shell, where the form's
  duplicate check never runs.

Lowercasing on save removes both. The local part of an address is technically
case-sensitive per RFC 5321, but no mail provider in practice treats it that
way, and Microsoft 365 certainly does not.
"""

from django.contrib.auth.models import User
from django.db.models.signals import pre_save
from django.dispatch import receiver


@receiver(pre_save, sender=User)
def normalise_email(sender, instance, **kwargs):
    """Store every address lowercase, whatever path created it."""
    if instance.email:
        instance.email = instance.email.strip().lower()
