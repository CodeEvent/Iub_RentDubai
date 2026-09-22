# Sets every account listed in documents/rentshield/dev_accounts.py to
# its own fresh, unique password -- what the login page's "Quick dev
# login" panel needs to populate per-account. Refuses outright unless
# settings.DEBUG is True: that's the one property this whole feature's
# safety rests on (the panel itself is also DEBUG-gated in
# documents/context_processors.py), so there's no path to a real
# deployment's accounts ever being touched by this.
from __future__ import annotations

import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from documents.rentshield.dev_accounts import DEV_ACCOUNTS
from documents.rentshield.dev_passwords import save_dev_passwords


class Command(BaseCommand):
    help = (
        "Sets every documents/rentshield/dev_accounts.py account to its own "
        "fresh, unique password, for the login page's Quick dev login "
        "panel. Refuses unless DEBUG is True."
    )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            self.stderr.write(
                self.style.ERROR(
                    "Refusing: DEBUG is not enabled. This command -- and the "
                    "login page's Quick dev login panel it supports -- only "
                    "ever runs in a DEBUG/dev environment, on purpose.",
                ),
            )
            return

        User = get_user_model()
        passwords: dict[str, str] = {}
        for account in DEV_ACCOUNTS:
            username = account["username"]
            user = User.objects.filter(username=username).first()
            if not user:
                self.stdout.write(
                    self.style.WARNING(f"Skipping {username!r}: no such user"),
                )
                continue
            password = secrets.token_urlsafe(9)
            user.set_password(password)
            user.save(update_fields=["password"])
            passwords[username] = password
            self.stdout.write(self.style.SUCCESS(f"{username}: {password}"))

        save_dev_passwords(passwords)

        self.stdout.write(
            self.style.WARNING(
                "Each account above now has its own unique password, saved "
                "to settings.DATA_DIR/rentshield_dev_passwords.json (not "
                "committed to git) for the Quick dev login panel to read. "
                "Any currently-logged-in session for one of these accounts "
                "will be signed out on its next request (Django invalidates "
                "a session's auth hash on password change).",
            ),
        )
