# A separate installed Django app, not another plain subpackage like
# documents/rentshield/ -- unlike a Notice (which only ever exists as a
# paperless-ngx Document + CustomFields, see documents/rentshield/), an
# Order has to exist BEFORE any Document does (payment happens before
# generation), so it needs a real database table and its own migrations
# rather than piggybacking on the Document/CustomField pattern.
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class RentshieldBillingConfig(AppConfig):
    name = "documents.rentshield_billing"
    label = "rentshield_billing"
    verbose_name = _("RentShield Billing")
