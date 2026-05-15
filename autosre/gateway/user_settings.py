"""
AutoSRE — User Integration Settings
Encrypted per-user API key storage with Fernet AES-256 encryption.
"""

import logging
import os
from typing import Dict, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from gateway.auth import get_current_user

logger = logging.getLogger("autosre.settings")

router = APIRouter(prefix="/settings", tags=["settings"])

# ─── Encryption ───
_FERNET_KEY = os.getenv("SETTINGS_ENCRYPTION_KEY", "")
_fernet = None

def _get_fernet():
    global _fernet
    if _fernet:
        return _fernet
    from cryptography.fernet import Fernet
    key = _FERNET_KEY
    if not key:
        # Auto-generate and warn
        key = Fernet.generate_key().decode()
        logger.warning("SETTINGS_ENCRYPTION_KEY not set — generated ephemeral key. Keys will be lost on restart!")
    _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet

def _encrypt(value: str) -> str:
    return _get_fernet().encrypt(value.encode()).decode()

def _decrypt(value: str) -> str:
    return _get_fernet().decrypt(value.encode()).decode()


# ─── Integration Definitions ───
INTEGRATION_SCHEMA = {
    "slack": {
        "label": "Slack",
        "icon": "💬",
        "fields": [
            {"key": "SLACK_BOT_TOKEN", "label": "Bot Token", "placeholder": "xoxb-...", "type": "password"},
            {"key": "SLACK_INCIDENT_CHANNEL", "label": "Channel", "placeholder": "#incidents", "type": "text"},
        ],
    },
    "github": {
        "label": "GitHub",
        "icon": "🐙",
        "fields": [
            {"key": "GITHUB_TOKEN", "label": "Personal Access Token", "placeholder": "ghp_...", "type": "password"},
            {"key": "GITHUB_REPO_OWNER", "label": "Repo Owner", "placeholder": "your-org", "type": "text"},
            {"key": "GITHUB_REPO_NAME", "label": "Repo Name", "placeholder": "your-repo", "type": "text"},
        ],
    },
    "jira": {
        "label": "Jira",
        "icon": "📋",
        "fields": [
            {"key": "JIRA_API_TOKEN", "label": "API Token", "placeholder": "ATATT3x...", "type": "password"},
            {"key": "JIRA_EMAIL", "label": "Email", "placeholder": "you@company.com", "type": "text"},
            {"key": "JIRA_URL", "label": "Jira URL", "placeholder": "https://yourorg.atlassian.net", "type": "text"},
            {"key": "JIRA_PROJECT_KEY", "label": "Project Key", "placeholder": "SRE", "type": "text"},
        ],
    },
    "email": {
        "label": "Email (SMTP)",
        "icon": "📧",
        "fields": [
            {"key": "SMTP_HOST", "label": "SMTP Host", "placeholder": "smtp.gmail.com", "type": "text"},
            {"key": "SMTP_PORT", "label": "SMTP Port", "placeholder": "587", "type": "text"},
            {"key": "SMTP_EMAIL", "label": "Email", "placeholder": "you@gmail.com", "type": "text"},
            {"key": "SMTP_PASSWORD", "label": "App Password", "placeholder": "xxxx xxxx xxxx xxxx", "type": "password"},
        ],
    },
    "langfuse": {
        "label": "Langfuse",
        "icon": "👁️",
        "fields": [
            {"key": "LANGFUSE_SECRET_KEY", "label": "Secret Key", "placeholder": "sk-lf-...", "type": "password"},
            {"key": "LANGFUSE_PUBLIC_KEY", "label": "Public Key", "placeholder": "pk-lf-...", "type": "text"},
            {"key": "LANGFUSE_BASE_URL", "label": "Base URL", "placeholder": "https://cloud.langfuse.com", "type": "text"},
        ],
    },
    "omium": {
        "label": "Omium",
        "icon": "🔍",
        "fields": [
            {"key": "OMIUM_API_KEY", "label": "API Key", "placeholder": "omium_...", "type": "password"},
        ],
    },
}


# ─── Models ───
class SaveIntegrationsRequest(BaseModel):
    integrations: Dict[str, Dict[str, str]]


# ─── DB Helpers ───
def _get_db():
    from memory.postgres_client import get_postgres
    return get_postgres()

def _save_setting(user_id: str, key: str, value: str):
    pg = _get_db()
    conn = pg._get_conn()
    if not conn:
        return
    encrypted = _encrypt(value)
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO user_settings (user_id, setting_key, encrypted_value, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (user_id, setting_key) DO UPDATE SET
                encrypted_value = EXCLUDED.encrypted_value,
                updated_at = NOW()
        """, (user_id, key, encrypted))

def _get_settings(user_id: str) -> Dict[str, str]:
    pg = _get_db()
    conn = pg._get_conn()
    if not conn:
        return {}
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT setting_key, encrypted_value FROM user_settings WHERE user_id = %s", (user_id,))
            rows = cur.fetchall()
        result = {}
        for key, enc_val in rows:
            try:
                result[key] = _decrypt(enc_val)
            except Exception:
                result[key] = ""
        return result
    except Exception as e:
        logger.error(f"Failed to get settings: {e}")
        return {}

def _delete_settings(user_id: str, keys: List[str]):
    pg = _get_db()
    conn = pg._get_conn()
    if not conn:
        return
    with conn.cursor() as cur:
        for key in keys:
            cur.execute("DELETE FROM user_settings WHERE user_id = %s AND setting_key = %s", (user_id, key))


# ─── Mask helper ───
def _mask(value: str) -> str:
    if not value or len(value) < 8:
        return "••••••"
    return value[:4] + "•" * (len(value) - 8) + value[-4:]


# ─── Endpoints ───
@router.get("/schema")
async def get_schema():
    """Return integration field definitions."""
    return {"integrations": INTEGRATION_SCHEMA}


@router.get("/integrations")
async def get_integrations(user: dict = Depends(get_current_user)):
    """Get user's configured integrations with masked keys."""
    settings = _get_settings(user["id"])
    result = {}
    for int_id, schema in INTEGRATION_SCHEMA.items():
        fields = {}
        configured = False
        for field in schema["fields"]:
            val = settings.get(field["key"], "")
            if val:
                configured = True
                fields[field["key"]] = _mask(val) if field["type"] == "password" else val
            else:
                fields[field["key"]] = ""
        result[int_id] = {"configured": configured, "fields": fields}
    return {"integrations": result}


@router.put("/integrations")
async def save_integrations(req: SaveIntegrationsRequest, user: dict = Depends(get_current_user)):
    """Save user's integration credentials (encrypted)."""
    saved = 0
    for int_id, fields in req.integrations.items():
        if int_id not in INTEGRATION_SCHEMA:
            continue
        for key, value in fields.items():
            # Skip masked values (unchanged)
            if "••••" in value:
                continue
            if value.strip():
                _save_setting(user["id"], key, value.strip())
                saved += 1
            else:
                _delete_settings(user["id"], [key])
    logger.info(f"User {user['email']} saved {saved} integration settings")
    return {"saved": saved, "message": f"Saved {saved} settings"}


@router.post("/integrations/test/{integration_id}")
async def test_integration(integration_id: str, user: dict = Depends(get_current_user)):
    """Test if a configured integration works."""
    settings = _get_settings(user["id"])
    
    if integration_id == "slack":
        token = settings.get("SLACK_BOT_TOKEN", "")
        if not token:
            return {"status": "not_configured"}
        try:
            from slack_sdk import WebClient
            client = WebClient(token=token)
            client.auth_test()
            return {"status": "connected"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif integration_id == "github":
        token = settings.get("GITHUB_TOKEN", "")
        if not token:
            return {"status": "not_configured"}
        try:
            import httpx
            r = httpx.get("https://api.github.com/user", headers={"Authorization": f"token {token}"}, timeout=5)
            if r.status_code == 200:
                return {"status": "connected", "user": r.json().get("login")}
            return {"status": "error", "message": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif integration_id == "jira":
        token = settings.get("JIRA_API_TOKEN", "")
        email = settings.get("JIRA_EMAIL", "")
        url = settings.get("JIRA_URL", "")
        if not (token and email and url):
            return {"status": "not_configured"}
        try:
            import httpx, base64
            creds = base64.b64encode(f"{email}:{token}".encode()).decode()
            r = httpx.get(f"{url}/rest/api/3/myself", headers={"Authorization": f"Basic {creds}"}, timeout=5)
            if r.status_code == 200:
                return {"status": "connected", "user": r.json().get("displayName")}
            return {"status": "error", "message": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif integration_id == "email":
        email = settings.get("SMTP_EMAIL", "")
        password = settings.get("SMTP_PASSWORD", "")
        host = settings.get("SMTP_HOST", "smtp.gmail.com")
        port = int(settings.get("SMTP_PORT", "587"))
        if not (email and password):
            return {"status": "not_configured"}
        try:
            import smtplib
            with smtplib.SMTP(host, port, timeout=5) as server:
                server.starttls()
                server.login(email, password)
            return {"status": "connected"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    return {"status": "unknown_integration"}
