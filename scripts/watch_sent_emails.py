#!/usr/bin/env python3
"""Live-tails src/sent_emails/ (Django's filebased EMAIL_BACKEND output
in this dev environment) and prints each new email as it's sent --
OTP codes, B2B teammate invites, etc. -- instead of manually running
`ls -t sent_emails/ | head -1` after every action that sends mail.

Usage: python3 scripts/watch_sent_emails.py [--interval SECONDS]

ponytail: plain polling loop, not inotify/watchdog -- this directory
gets at most a few files a minute during manual testing, so a 1s
poll is indistinguishable from a real filesystem watch here and needs
no new dependency. Switch to watchdog if this ever needs to react to
high-frequency writes.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

SENT_EMAILS_DIR = Path(__file__).resolve().parent.parent / "src" / "sent_emails"


def _print_email(path: Path) -> None:
    text = path.read_text(errors="replace")
    subject = to = ""
    for line in text.splitlines():
        if line.startswith("Subject: "):
            subject = line.removeprefix("Subject: ")
        elif line.startswith("To: "):
            to = line.removeprefix("To: ")
        if subject and to:
            break
    body = text.split("\n\n", 1)[1] if "\n\n" in text else text
    print(f"\n=== {path.name} ===")
    print(f"To: {to}")
    print(f"Subject: {subject}")
    print(body.strip())
    print("=" * (len(path.name) + 8))


def main() -> None:
    # Line-buffer stdout even when redirected to a file/pipe (not a
    # TTY) -- otherwise Python block-buffers it and output only shows
    # up once the buffer fills or the process exits, which for a
    # long-running watcher means "never, until you kill it."
    sys.stdout.reconfigure(line_buffering=True)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", type=float, default=1.0, help="poll interval in seconds")
    args = parser.parse_args()

    if not SENT_EMAILS_DIR.is_dir():
        print(f"No such directory: {SENT_EMAILS_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"Watching {SENT_EMAILS_DIR} for new emails (Ctrl-C to stop)...")
    # Only ever prints emails sent AFTER this script starts -- the
    # directory already holds this whole session's test history, and
    # replaying all of it on every start would be exactly the noisy
    # behavior this script exists to avoid.
    seen = set(SENT_EMAILS_DIR.iterdir())

    try:
        while True:
            time.sleep(args.interval)
            current = set(SENT_EMAILS_DIR.iterdir())
            for path in sorted(current - seen):
                _print_email(path)
            seen = current
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
