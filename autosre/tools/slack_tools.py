"""
AutoSRE — Slack Tools
Post incident messages, create threads, and send notifications via Slack API.
Gracefully falls back to console logging if no token is configured.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from config import settings

logger = logging.getLogger("autosre.tools.slack")


def _get_slack_client():
    """Get Slack WebClient, or None if unavailable."""
    if not settings.has_slack():
        return None
    try:
        from slack_sdk import WebClient
        return WebClient(token=settings.SLACK_BOT_TOKEN)
    except ImportError:
        logger.warning("slack_sdk not installed")
        return None
    except Exception as e:
        logger.warning(f"Slack client init failed: {e}")
        return None


def post_message(
    channel: str = None,
    text: str = "",
    blocks: List[Dict] = None,
    thread_ts: str = None,
) -> Dict[str, Any]:
    """Post a message to a Slack channel.
    
    Supports rich Block Kit formatting for incident updates.
    """
    channel = channel or settings.SLACK_INCIDENT_CHANNEL

    logger.info(f"[slack] Posting to {channel}: {text[:100]}...")

    client = _get_slack_client()
    if client:
        try:
            kwargs = {"channel": channel, "text": text}
            if blocks:
                kwargs["blocks"] = blocks
            if thread_ts:
                kwargs["thread_ts"] = thread_ts

            response = client.chat_postMessage(**kwargs)
            return {
                "status": "posted",
                "channel": channel,
                "ts": response["ts"],
                "message_preview": text[:200],
            }
        except Exception as e:
            logger.error(f"[slack] Failed to post message: {e}")
            return {"status": "error", "error": str(e)}
    else:
        logger.info(f"[slack] SIMULATED message to {channel}:\n{text}")
        return {
            "status": "simulated",
            "channel": channel,
            "ts": "1234567890.123456",
            "message_preview": text[:200],
            "note": "Slack integration simulated — no token configured",
        }


def create_incident_thread(
    incident_id: str,
    title: str,
    severity: str,
    description: str,
    channel: str = None,
) -> Dict[str, Any]:
    """Create a structured incident thread in Slack with rich formatting."""
    channel = channel or settings.SLACK_INCIDENT_CHANNEL

    severity_emoji = {
        "critical": "🔴",
        "high": "🟠",
        "medium": "🟡",
        "low": "🟢",
    }
    emoji = severity_emoji.get(severity, "⚪")

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} {incident_id} | {title}",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Severity:*\n{severity.upper()}"},
                {"type": "mrkdwn", "text": f"*Status:*\nInvestigating"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Description:*\n{description[:500]}",
            },
        },
        {"type": "divider"},
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "🤖 _AutoSRE is investigating this incident autonomously..._",
                }
            ],
        },
    ]

    text = f"{emoji} {incident_id} | {title} [{severity.upper()}]\n{description}"

    return post_message(channel=channel, text=text, blocks=blocks)


def post_diagnosis_update(
    thread_ts: str,
    incident_id: str,
    root_cause: str,
    confidence: float,
    recommendation: str,
    similar_incident: str = None,
    channel: str = None,
) -> Dict[str, Any]:
    """Post a diagnosis update to an existing incident thread."""
    channel = channel or settings.SLACK_INCIDENT_CHANNEL

    text_parts = [
        f"🔍 *Diagnosis for {incident_id}*",
        f"",
        f"*Root Cause:* {root_cause}",
        f"*Confidence:* {confidence:.0%}",
        f"*Recommendation:* {recommendation}",
    ]
    if similar_incident:
        text_parts.append(f"*Similar Past Incident:* {similar_incident}")

    text = "\n".join(text_parts)

    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": text},
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Acknowledge"},
                    "style": "primary",
                    "value": incident_id,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🔄 Rollback"},
                    "style": "danger",
                    "value": f"rollback:{incident_id}",
                },
            ],
        },
    ]

    return post_message(channel=channel, text=text, blocks=blocks, thread_ts=thread_ts)


def post_resolution_update(
    thread_ts: str,
    incident_id: str,
    summary: str,
    actions_taken: List[str],
    channel: str = None,
) -> Dict[str, Any]:
    """Post a resolution summary to the incident thread."""
    channel = channel or settings.SLACK_INCIDENT_CHANNEL

    actions_text = "\n".join(f"  • {a}" for a in actions_taken)
    text = (
        f"✅ *{incident_id} — Resolution Summary*\n\n"
        f"{summary}\n\n"
        f"*Actions Taken:*\n{actions_text}"
    )

    return post_message(channel=channel, text=text, thread_ts=thread_ts)


def send_email(to: str, subject: str, body: str) -> Dict[str, Any]:
    """Send an email notification (simulated — would use SMTP or SendGrid in production)."""
    logger.info(f"[email] SIMULATED email to {to}: {subject}")
    return {
        "status": "simulated",
        "to": to,
        "subject": subject,
        "body_preview": body[:200],
        "note": "Email integration simulated. In production, this would use SMTP or SendGrid.",
    }
