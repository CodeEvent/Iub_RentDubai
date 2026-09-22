# Extends django-allauth's signup form via its own documented extension
# point (ACCOUNT_SIGNUP_FORM_CLASS -- see
# allauth.account.internal.flows.signup.base_signup_form_class):
# signup(self, request, user) runs once the new user is created.
#
# Property Owner is RentShield's only self-service role (see README's
# dated "Roles simplified" section) -- every self-serve signup joins it
# unconditionally, with no user choice. This form used to also offer a
# Tenant choice; that role was cut for having no working per-notice
# visibility. Admin accounts are createsuperuser/Django-admin only, not
# something anyone can get via this signup form.
from __future__ import annotations

from django import forms

from documents.rentshield.roles import grant_property_owner


class RentShieldSignupExtra(forms.Form):
    def signup(self, request, user):
        grant_property_owner(user)
