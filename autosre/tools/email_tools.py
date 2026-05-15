"""
AutoSRE — Email Notification Tool
Sends HTML incident reports via SMTP (Gmail compatible).
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Any, Dict, List, Optional

from config import settings

logger = logging.getLogger("autosre.tools.email")


def send_email(to: str, subject: str, body_html: str, body_text: str = "") -> Dict[str, Any]:
    """Send an email notification via SMTP."""
    if not settings.has_email():
        logger.info(f"[email] SIMULATED → {to}: {subject}")
        return {"status": "simulated", "to": to, "subject": subject,
                "note": "SMTP not configured. Set SMTP_EMAIL and SMTP_PASSWORD in .env"}

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"AutoSRE <{settings.SMTP_EMAIL}>"
        msg["To"] = to
        msg["Subject"] = subject

        if body_text:
            msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_EMAIL, settings.SMTP_PASSWORD)
            server.send_message(msg)

        logger.info(f"[email] Sent to {to}: {subject}")
        return {"status": "sent", "to": to, "subject": subject}

    except Exception as e:
        logger.error(f"[email] Failed: {e}")
        return {"status": "failed", "error": str(e), "to": to, "subject": subject}


def send_incident_email(incident_id: str, title: str, severity: str,
                        root_cause: str, confidence: float,
                        recommendation: str, to: Optional[str] = None) -> Dict[str, Any]:
    """Send a formatted incident resolution email."""
    recipient = to or settings.SMTP_EMAIL or "sre-team@company.com"

    severity_colors = {
        "critical": "#FF4757", "high": "#FF9100",
        "medium": "#FFD600", "low": "#00E676",
    }
    color = severity_colors.get(severity, "#FF9100")

    html = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #0a0e1a; color: #f0f4ff; padding: 0; border-radius: 12px; overflow: hidden;">
        <div style="background: linear-gradient(135deg, #00F0FF, #7B61FF); padding: 24px 30px;">
            <h1 style="margin: 0; font-size: 20px; color: #0a0e1a;">🛡️ AutoSRE Incident Report</h1>
        </div>
        <div style="padding: 24px 30px;">
            <div style="background: #1a1f35; border-radius: 8px; padding: 16px; margin-bottom: 16px; border-left: 4px solid {color};">
                <p style="margin: 0 0 4px; font-size: 12px; color: #8b95b5; text-transform: uppercase;">Incident</p>
                <h2 style="margin: 0; font-size: 18px;">{incident_id}</h2>
                <p style="margin: 4px 0 0; color: #8b95b5;">{title}</p>
            </div>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 16px;">
                <tr>
                    <td style="padding: 10px; background: #1a1f35; border-radius: 8px; text-align: center; width: 50%;">
                        <span style="color: {color}; font-weight: 700; font-size: 14px; text-transform: uppercase;">{severity}</span>
                        <br><span style="font-size: 11px; color: #8b95b5;">Severity</span>
                    </td>
                    <td style="width: 8px;"></td>
                    <td style="padding: 10px; background: #1a1f35; border-radius: 8px; text-align: center; width: 50%;">
                        <span style="color: #00F0FF; font-weight: 700; font-size: 14px;">{confidence:.0%}</span>
                        <br><span style="font-size: 11px; color: #8b95b5;">Confidence</span>
                    </td>
                </tr>
            </table>
            <div style="background: #1a1f35; border-radius: 8px; padding: 16px; margin-bottom: 16px;">
                <p style="margin: 0 0 8px; font-size: 12px; color: #00F0FF; text-transform: uppercase; font-weight: 600;">🔍 Root Cause</p>
                <p style="margin: 0; font-family: 'Courier New', monospace; color: #00E676; background: rgba(0,0,0,0.3); padding: 10px; border-radius: 6px; font-size: 13px;">{root_cause}</p>
            </div>
            <div style="background: #1a1f35; border-radius: 8px; padding: 16px; margin-bottom: 16px;">
                <p style="margin: 0 0 8px; font-size: 12px; color: #00F0FF; text-transform: uppercase; font-weight: 600;">💡 Recommendation</p>
                <p style="margin: 0; color: #f0f4ff; font-size: 14px;">{recommendation}</p>
            </div>
            <div style="text-align: center; padding: 16px 0 8px;">
                <p style="margin: 0; font-size: 11px; color: #5a6380;">
                    Diagnosed autonomously by AutoSRE • Powered by Ollama ({settings.OLLAMA_MODEL})
                </p>
            </div>
        </div>
    </div>
    """

    text = f"""
AutoSRE Incident Report
========================
Incident: {incident_id}
Title: {title}
Severity: {severity}
Root Cause: {root_cause}
Confidence: {confidence:.0%}
Recommendation: {recommendation}
    """

    return send_email(
        to=recipient,
        subject=f"[AutoSRE] {severity.upper()} — {incident_id}: {title}",
        body_html=html,
        body_text=text.strip(),
    )
