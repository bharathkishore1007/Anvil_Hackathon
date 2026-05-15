"""
AutoSRE — Authentication Module
JWT-based auth with bcrypt password hashing. Users stored in PostgreSQL.
"""

import logging
import os
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends, Header, Request
from pydantic import BaseModel

logger = logging.getLogger("autosre.auth")

router = APIRouter(prefix="/auth", tags=["auth"])

# ─── Config ───
JWT_SECRET = os.getenv("JWT_SECRET", "autosre-jwt-secret-2026-change-in-prod")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 72

# ─── Rate Limiting ───
_rate_limits = defaultdict(list)  # IP -> [timestamps]
RATE_LIMIT_MAX = 5  # max attempts
RATE_LIMIT_WINDOW = 60  # per 60 seconds

def _check_rate_limit(request: Request):
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    _rate_limits[ip] = [t for t in _rate_limits[ip] if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_limits[ip]) >= RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Too many attempts. Please try again later.")
    _rate_limits[ip].append(now)


# ─── Models ───
class SignupRequest(BaseModel):
    name: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: str
    name: str
    email: str


# ─── Password Hashing ───
def _hash_password(password: str) -> str:
    import bcrypt
    pwd = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pwd, bcrypt.gensalt()).decode("utf-8")

def _verify_password(plain: str, hashed: str) -> bool:
    import bcrypt
    pwd = plain.encode("utf-8")[:72]
    return bcrypt.checkpw(pwd, hashed.encode("utf-8"))


# ─── JWT ───
def _create_token(user_id: str, email: str, name: str) -> str:
    from jose import jwt
    payload = {
        "sub": user_id,
        "email": email,
        "name": name,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def _decode_token(token: str) -> dict:
    from jose import jwt, JWTError
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None


# ─── DB Helpers ───
def _get_db():
    from memory.postgres_client import get_postgres
    return get_postgres()

def _ensure_auth_tables():
    """Create auth tables if not exist."""
    pg = _get_db()
    conn = pg._get_conn()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS user_settings (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id),
                    setting_key TEXT NOT NULL,
                    encrypted_value TEXT NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(user_id, setting_key)
                );
            """)
        logger.info("Auth tables verified")
    except Exception as e:
        logger.warning(f"Auth tables check failed: {e}")


# ─── Dependency: Get Current User ───
async def get_current_user(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1]
    payload = _decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"id": payload["sub"], "email": payload["email"], "name": payload["name"]}


# ─── Endpoints ───
@router.post("/signup")
async def signup(req: SignupRequest, request: Request):
    """Register a new user."""
    _check_rate_limit(request)
    try:
        _ensure_auth_tables()
    except Exception as e:
        logger.error(f"Table creation failed: {e}")

    pg = _get_db()
    conn = pg._get_conn()
    if not conn:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    # Check if email exists
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE email = %s", (req.email.lower(),))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Email already registered")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signup check failed: {e}")
        raise HTTPException(status_code=500, detail="Registration failed. Please try again.")

    # Create user
    user_id = str(uuid.uuid4())[:8]
    try:
        password_hash = _hash_password(req.password)
    except Exception as e:
        logger.error(f"Password hash failed: {e}")
        raise HTTPException(status_code=500, detail=f"Hash error: {e}")

    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (id, name, email, password_hash) VALUES (%s, %s, %s, %s)",
                (user_id, req.name, req.email.lower(), password_hash),
            )
    except Exception as e:
        logger.error(f"User insert failed: {e}")
        raise HTTPException(status_code=500, detail="Registration failed. Please try again.")

    token = _create_token(user_id, req.email.lower(), req.name)
    logger.info(f"User registered: {req.email}")
    return {"token": token, "user": {"id": user_id, "name": req.name, "email": req.email.lower()}}


@router.post("/login")
async def login(req: LoginRequest, request: Request):
    """Authenticate and return JWT."""
    _check_rate_limit(request)
    _ensure_auth_tables()
    pg = _get_db()
    conn = pg._get_conn()
    if not conn:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, email, password_hash FROM users WHERE email = %s", (req.email.lower(),))
            row = cur.fetchone()
    except Exception as e:
        logger.error(f"Login query failed: {e}")
        raise HTTPException(status_code=500, detail="Login failed. Please try again.")

    if not row:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user_id, name, email, password_hash = row
    if not _verify_password(req.password, password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = _create_token(user_id, email, name)
    logger.info(f"User logged in: {email}")
    return {"token": token, "user": {"id": user_id, "name": name, "email": email}}


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Get current user info."""
    return {"user": user}


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
async def change_password(req: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    """Change the current user's password."""
    pg = _get_db()
    conn = pg._get_conn()
    if not conn:
        raise HTTPException(status_code=503, detail="Database unavailable")

    # Get current hash
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT password_hash FROM users WHERE id = %s", (user["id"],))
            row = cur.fetchone()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify current password
    if not _verify_password(req.current_password, row[0]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    # Update password
    new_hash = _hash_password(req.new_password)
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (new_hash, user["id"]))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    logger.info(f"Password changed for user {user['email']}")
    return {"message": "Password updated successfully"}
