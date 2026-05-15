"""
AutoSRE — Authentication Module
JWT-based auth with bcrypt password hashing. Users stored in PostgreSQL.
"""

import logging
import os
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel

logger = logging.getLogger("autosre.auth")

router = APIRouter(prefix="/auth", tags=["auth"])

# ─── Config ───
JWT_SECRET = os.getenv("JWT_SECRET", "autosre-jwt-secret-2026-change-in-prod")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 72


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
async def signup(req: SignupRequest):
    """Register a new user."""
    try:
        _ensure_auth_tables()
    except Exception as e:
        logger.error(f"Table creation failed: {e}")

    pg = _get_db()
    conn = pg._get_conn()
    if not conn:
        raise HTTPException(status_code=503, detail="Database unavailable")

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
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

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
        raise HTTPException(status_code=500, detail=f"Insert error: {e}")

    token = _create_token(user_id, req.email.lower(), req.name)
    logger.info(f"User registered: {req.email}")
    return {"token": token, "user": {"id": user_id, "name": req.name, "email": req.email.lower()}}


@router.post("/login")
async def login(req: LoginRequest):
    """Authenticate and return JWT."""
    _ensure_auth_tables()
    pg = _get_db()
    conn = pg._get_conn()
    if not conn:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, email, password_hash FROM users WHERE email = %s", (req.email.lower(),))
            row = cur.fetchone()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
