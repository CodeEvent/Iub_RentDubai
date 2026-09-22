from django.conf import settings as django_settings
from django.contrib.auth.models import User

from documents.models import Document
from documents.rentshield.dev_accounts import DEV_ACCOUNTS
from documents.rentshield.dev_passwords import load_dev_passwords
from paperless.config import GeneralConfig


def settings(request):
    general_config = GeneralConfig()

    app_title = (
        django_settings.APP_TITLE
        if general_config.app_title is None or len(general_config.app_title) == 0
        else general_config.app_title
    )
    app_logo = (
        django_settings.APP_LOGO
        if general_config.app_logo is None or len(general_config.app_logo) == 0
        else django_settings.BASE_URL + general_config.app_logo.lstrip("/")
    )

    return {
        "EMAIL_ENABLED": django_settings.EMAIL_ENABLED,
        "DISABLE_REGULAR_LOGIN": django_settings.DISABLE_REGULAR_LOGIN,
        "REDIRECT_LOGIN_TO_SSO": django_settings.REDIRECT_LOGIN_TO_SSO,
        "ACCOUNT_ALLOW_SIGNUPS": django_settings.ACCOUNT_ALLOW_SIGNUPS,
        "domain": getattr(django_settings, "PAPERLESS_URL", request.get_host()),
        "APP_TITLE": app_title,
        "APP_LOGO": app_logo,
        "FIRST_INSTALL": User.objects.exclude(
            username__in=["consumer", "AnonymousUser"],
        ).count()
        == 0
        and Document.global_objects.count() == 0,
        # RentShield's "Quick dev login" panel on the sign-in page --
        # DEBUG-gated here, not just in the template, so the login page
        # has no way to render real account usernames/passwords unless
        # this is already a dev environment. Each account's password
        # comes from the (gitignored) file manage.py
        # set_rentshield_dev_passwords writes -- see documents/rentshield/
        # dev_accounts.py and dev_passwords.py. An account with no
        # entry there yet (command never run) is simply left out, not
        # shown with a broken/empty password.
        "RENTSHIELD_DEV_ACCOUNTS": _dev_accounts_with_passwords() if django_settings.DEBUG else [],
    }


def _dev_accounts_with_passwords() -> list[dict]:
    passwords = load_dev_passwords()
    return [
        {**account, "password": passwords[account["username"]]}
        for account in DEV_ACCOUNTS
        if account["username"] in passwords
    ]
