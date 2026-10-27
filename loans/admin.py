from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html

from .emails import send_setup_link, set_unguessable_password


class UserCreateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        self.fields["email"].help_text = (
            "The setup link is sent here. It cannot be changed by the user "
            "afterwards without an administrator."
        )

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A user with that email address already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        set_unguessable_password(user)
        if commit:
            user.save()
        return user


admin.site.unregister(User)


@admin.register(User)
class PortalUserAdmin(UserAdmin):
    add_form = UserCreateForm
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "description": (
                    "The new user is emailed a link to choose their own password. "
                    "You will not see or set one."
                ),
                "fields": ("username", "email", "first_name", "last_name"),
            },
        ),
    )
    list_display = (
        "username", "email", "first_name", "last_name", "is_active",
        "is_staff", "password_state", "last_login",
    )
    list_filter = ("is_active", "is_staff", "is_superuser", "last_login")
    actions = ["send_setup_email"]
    change_form_template = "admin/auth/user/change_form.html"

    @admin.display(description="Signed in yet?", boolean=False)
    def password_state(self, user):
        if user.last_login:
            return "Yes"
        return format_html('<span style="color:#8A5A00">Never signed in</span>')


    @admin.action(description="Send password setup email")
    def send_setup_email(self, request, queryset):
        sent, skipped = 0, []
        for user in queryset:
            if send_setup_link(user, request, new_account=not user.last_login):
                sent += 1
            else:
                skipped.append(user.get_username())

        if sent:
            self.message_user(
                request,
                f"Setup link sent to {sent} user{'s' if sent != 1 else ''}.",
                messages.SUCCESS,
            )
        if skipped:
            self.message_user(
                request,
                "No link sent to "
                + ", ".join(skipped)
                + " - the account needs a valid email address and must be active.",
                messages.WARNING,
            )

    def get_urls(self):
        return [
            path(
                "<int:user_id>/send-setup-email/",
                self.admin_site.admin_view(self.send_setup_email_view),
                name="auth_user_send_setup_email",
            ),
        ] + super().get_urls()

    def send_setup_email_view(self, request, user_id):
        user = User.objects.filter(pk=user_id).first()
        if user is None:
            self.message_user(request, "No such user.", messages.ERROR)
            return HttpResponseRedirect(reverse("admin:auth_user_changelist"))

        if send_setup_link(user, request, new_account=not user.last_login):
            self.message_user(
                request, f"Setup link sent to {user.email}.", messages.SUCCESS
            )
        else:
            self.message_user(
                request,
                f"No link sent to {user.get_username()} - the account needs a "
                "valid email address and must be active.",
                messages.WARNING,
            )
        return HttpResponseRedirect(
            reverse("admin:auth_user_change", args=[user.pk])
        )


    def response_add(self, request, obj, post_url_continue=None):
        if send_setup_link(obj, request, new_account=True):
            self.message_user(
                request,
                f"{obj.get_username()} created. A link to set a password has "
                f"been emailed to {obj.email}.",
                messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                f"{obj.get_username()} created, but no setup email could be "
                "sent. Check the address and use “Send password setup email”.",
                messages.WARNING,
            )
        return super().response_add(request, obj, post_url_continue)
