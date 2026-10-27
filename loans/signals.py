from django.contrib.auth.models import User
from django.db.models.signals import pre_save
from django.dispatch import receiver


@receiver(pre_save, sender=User)
def normalise_email(sender, instance, **kwargs):
    if instance.email:
        instance.email = instance.email.strip().lower()
