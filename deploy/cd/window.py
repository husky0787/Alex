"""Refuse billable provisioning outside the operator's current reviewed window."""
from datetime import datetime, timedelta, timezone
import os


def check_window(value, now=None):
    now = now or datetime.now(timezone.utc)
    expiry = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if expiry.tzinfo is None or not now + timedelta(hours=2) <= expiry <= now + timedelta(days=1):
        raise ValueError('Cloud window must leave 2 hours and expire within 24 hours; refresh billing review')
    return expiry


if __name__ == '__main__':
    if os.environ.get('RECOVERY_ENABLED') != 'true':
        raise SystemExit('Enable the independent recovery workflow before provisioning')
    check_window(os.environ.get('APPROVED_UNTIL', ''))
    print('Current reviewed cloud window confirmed (not an AWS spending cap)')
