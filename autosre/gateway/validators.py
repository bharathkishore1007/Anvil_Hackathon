"""
AutoSRE — Webhook Validators
HMAC signature verification for PagerDuty, GitHub, and Slack webhooks.
"""

import hashlib
import hmac
import time
from typing import Optional

from config import settings


def verify_pagerduty_signature(body: bytes, signature: Optional[str]) -> bool:
    """Verify PagerDuty webhook HMAC-SHA256 signature."""
    secret = settings.PAGERDUTY_WEBHOOK_SECRET
    if not secret:
        # No secret configured — accept all (dev mode)
        return True
    if not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"v1={expected}", signature)


def verify_github_signature(body: bytes, signature: Optional[str]) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature."""
    secret = settings.GITHUB_WEBHOOK_SECRET
    if not secret:
        return True
    if not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


def verify_slack_signature(body: bytes, timestamp: Optional[str], signature: Optional[str]) -> bool:
    """Verify Slack request signature using signing secret."""
    secret = settings.SLACK_SIGNING_SECRET
    if not secret:
        return True
    if not timestamp or not signature:
        return False
    # Reject requests older than 5 minutes
    if abs(time.time() - float(timestamp)) > 300:
        return False
    base = f"v0:{timestamp}:{body.decode()}"
    expected = hmac.new(secret.encode(), base.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"v0={expected}", signature)
