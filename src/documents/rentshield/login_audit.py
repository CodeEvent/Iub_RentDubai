# Backs the admin dashboard's "Last 10 Logins" table (documents/admin_views.py)
# with data Django already owns, instead of reaching into Authelia's own
# internal sqlite file -- that schema is undocumented and not meant to
# be read by other services. Connected to django.contrib.auth's
# built-in user_logged_in signal in documents/apps.py's ready(), which
# already fires after every successful login regardless of backend --
# with PAPERLESS_DISABLE_REGULAR_LOGIN=true, every login here is an
# OIDC login, so no extra backend-detection logic is needed.
from documents.models import RentShieldLoginLog


def record_login(sender, request, user, **kwargs):
    RentShieldLoginLog.objects.create(user=user)
