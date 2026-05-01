import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from dotenv import load_dotenv

load_dotenv()

# Password hashing configuration
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-default-secret-key-for-dev-only")
ALGORITHM = os.getenv("ALGORITHM", "HS256")

# ── Token Lifetimes ──────────────────────────────────────────────────
ACCESS_TOKEN_EXPIRE_MINUTES = 15           # Short-lived access token
REFRESH_TOKEN_EXPIRE_DAYS = 7              # Long-lived refresh token
HARD_LIMIT_HOURS = 24                      # Absolute session limit from login time
INACTIVITY_TIMEOUT_MINUTES = 15            # Matches access token lifetime

# Legacy export (kept for backward compat with .env override if present)
_env_access = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")
if _env_access:
    ACCESS_TOKEN_EXPIRE_MINUTES = int(_env_access)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check if the plain password matches the hashed one."""
    if not hashed_password:
        return False
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate a bcrypt hash of the password."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Generate a short-lived JWT access token.

    Includes an `iat` (issued-at) claim so the backend can enforce hard
    session limits independently of the token's own expiry.
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)

    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "iat": now})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT access token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def generate_refresh_token() -> str:
    """Create a cryptographically random opaque refresh token string."""
    return str(uuid.uuid4())
