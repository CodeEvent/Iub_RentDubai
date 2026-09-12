# A separate installed Django app, same reasoning as
# documents/rentshield_billing/apps.py: IdentityVerification needs a
# real row (and status) that exists independently of any Document --
# a property owner can be identity-verified without ever having
# generated a notice -- so it doesn't fit the Document/CustomField
# pattern documents/rentshield/ uses everywhere else.
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class RentshieldIdentityConfig(AppConfig):
    name = "documents.rentshield_identity"
    label = "rentshield_identity"
    verbose_name = _("RentShield Identity Verification")
