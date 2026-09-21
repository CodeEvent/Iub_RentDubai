# Where manage.py set_rentshield_dev_passwords writes the per-account
# plaintext passwords it just generated, and where
# documents/context_processors.py reads them back to populate the login
# page's "Quick dev login" panel. Lives under settings.DATA_DIR -- same
# already-gitignored runtime-data location documents/rentshield/
# notary_research/ uses for its own local-only JSON snapshots -- so
# these plaintext dev passwords never reach git, regardless of the
# DEBUG gate every other part of this feature also has.
from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings


def _path() -> Path:
    return Path(settings.DATA_DIR) / "rentshield_dev_passwords.json"


def load_dev_passwords() -> dict[str, str]:
    """username -> plaintext password, or {} if the command has never
    been run (or the file was deleted) -- callers treat that as "no
    working quick-login password for anyone yet", not an error."""
    path = _path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def save_dev_passwords(passwords: dict[str, str]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(passwords, indent=2))
