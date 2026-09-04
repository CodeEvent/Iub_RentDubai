# Extends django-allauth's signup form with a role choice, via its own
# documented extension point (ACCOUNT_SIGNUP_FORM_CLASS -- see
# allauth.account.internal.flows.signup.base_signup_form_class): any
# fields declared here are merged into the real signup form, and
# signup(self, request, user) runs once the new user is created.
#
# Only Property Owner and Tenant are self-service roles. Notary and
# Lawyer represent a real-world vetted professional relationship (a
# licensed notary, a retained lawyer) -- those are assigned by an admin
# under Settings > Users & Groups, not something anyone can declare
# about themselves at signup.
from __future__ import annotations

from django import forms
from django.contrib.auth.models import Group

from documents.rentshield.roles import PROPERTY_OWNER_GROUP_NAME
from documents.rentshield.roles import TENANT_GROUP_NAME

ROLE_CHOICES = [
    (PROPERTY_OWNER_GROUP_NAME, "Property Owner / Landlord"),
    (TENANT_GROUP_NAME, "Tenant"),
]


class RentShieldSignupExtra(forms.Form):
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.RadioSelect,
        initial=PROPERTY_OWNER_GROUP_NAME,
        label="I am a",
    )

    def signup(self, request, user):
        group = Group.objects.filter(name=self.cleaned_data["role"]).first()
        if group:
            user.groups.add(group)
