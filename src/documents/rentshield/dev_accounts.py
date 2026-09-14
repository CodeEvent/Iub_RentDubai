# Demo/dev-only account list for the "Quick dev login" panel on the
# sign-in page (documents/templates/account/login.html). Usernames and
# role labels aren't secret -- only the shared password is, and that's
# entirely settings.DEBUG-gated (see documents/context_processors.py's
# settings() and manage.py set_rentshield_dev_passwords), so this list
# reaching production code is harmless: DEBUG=False means the login
# page never renders the panel and the reset command refuses to run.
DEV_ACCOUNTS = [
    {"username": "admin", "label": "Admin (superuser)"},
    {"username": "notary", "label": "Notary Public (fulfillment)"},
    {"username": "Property_Ownwer2", "label": "Property Owner"},
]
