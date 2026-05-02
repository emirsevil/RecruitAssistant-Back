from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, WebSocket
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import os

from database import get_db
import schemas.user as schemas
import crud.user as crud
import crud.refresh_token as refresh_crud
from utils.auth import (
    verify_password,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    HARD_LIMIT_HOURS,
)
import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

COOKIE_NAME = "access_token"
REFRESH_COOKIE_NAME = "refresh_token"
IS_PRODUCTION = os.getenv("ENVIRONMENT", "development") == "production"

# ── Cookie helpers ────────────────────────────────────────────────────

def _cookie_opts() -> dict:
    """Shared cookie options for consistency."""
    return dict(
        httponly=True,
        samesite="lax" if not IS_PRODUCTION else "none",
        secure=IS_PRODUCTION,
        path="/",
    )


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    """Set both access and refresh token cookies on the response."""
    opts = _cookie_opts()
    response.set_cookie(
        key=COOKIE_NAME,
        value=access_token,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        expires=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        **opts,
    )
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        expires=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        **opts,
    )


def _clear_auth_cookies(response: Response):
    """Remove both auth cookies."""
    opts = _cookie_opts()
    response.delete_cookie(key=COOKIE_NAME, **opts)
    response.delete_cookie(key=REFRESH_COOKIE_NAME, **opts)


# ── In-memory WebSocket ticket store ─────────────────────────────────
import uuid
import time
ws_tickets = {}
TICKET_EXPIRY_SECONDS = 60

from typing import Union

# ── Current-user dependencies ────────────────────────────────────────

async def _get_current_user_base(cookies: dict, db: Session):
    token = cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    email: str = payload.get("sub")
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    user = crud.get_user_by_email(db, email=email)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user

async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Dependency to extract and verify the user from the HttpOnly cookie (HTTP)."""
    return await _get_current_user_base(request.cookies, db)

async def get_current_user_ws(websocket: WebSocket, db: Session = Depends(get_db)):
    """Dependency to extract and verify the user from the HttpOnly cookie OR a query ticket (WebSocket)."""
    # 1. Try Ticket from query params (Cross-Origin fallback)
    ticket = websocket.query_params.get("ticket")
    msg = f"[WS-AUTH] Incoming connection attempt. Ticket in URL: {ticket}"
    print(msg)
    logger.info(msg)

    if ticket:
        if ticket in ws_tickets:
            ticket_data = ws_tickets.pop(ticket) # One-time use
            msg = f"[WS-AUTH] Found ticket in memory. UserID: {ticket_data['user_id']}, Expiry: {ticket_data['expires']}"
            print(msg)
            logger.info(msg)

            if time.time() < ticket_data["expires"]:
                user = crud.get_user(db, user_id=ticket_data["user_id"])
                if user:
                    msg = f"[WS-AUTH] Ticket valid. Authenticated as user: {user.email}"
                    print(msg)
                    logger.info(msg)
                    return user
                print("[WS-AUTH] Ticket valid but user not found in DB.")
            else:
                print(f"[WS-AUTH] Ticket expired. Current time: {time.time()}, Expiry: {ticket_data['expires']}")
        else:
            print("[WS-AUTH] Ticket not found in memory (invalid or already used).")

    # 2. Try Cookie (Default)
    print("[WS-AUTH] Falling back to cookie authentication...")
    try:
        user = await _get_current_user_base(websocket.cookies, db)
        print(f"[WS-AUTH] Cookie auth successful. User: {user.email}")
        return user
    except Exception as e:
        msg = f"[WS-AUTH] Authentication failed miserably: {str(e)}"
        print(msg)
        logger.error(msg)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="WebSocket authentication failed",
        )

# ── Endpoints ────────────────────────────────────────────────────────

@router.post("/register", response_model=schemas.UserResponse)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """API endpoint to register a new user."""
    db_user = crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    return crud.create_user(db=db, user=user)

@router.post("/login")
def login(
    response: Response,
    credentials: schemas.UserLogin,
    db: Session = Depends(get_db)
):
    """Login → issue short-lived access token + DB-backed refresh token."""
    user = crud.get_user_by_email(db, email=credentials.email)
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Cookie"},
        )

    now = datetime.now(timezone.utc)

    # Access token (15 min)
    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    # Refresh token (7 days, stored in DB)
    raw_refresh = generate_refresh_token()
    refresh_crud.create_refresh_token(
        db=db,
        user_id=user.id,
        token=raw_refresh,
        expires_at=now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        login_time=now,
    )

    # Set cookies
    _set_auth_cookies(response, access_token, raw_refresh)

    return {
        "message": "Successfully logged in",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "education": user.education,
            "phone": user.phone,
            "address": user.address,
            "bio": user.bio,
            "professional_title": user.professional_title,
            "skills": user.skills,
            "profile_image": user.profile_image,
            "base_cv": user.base_cv,
        },
    }


@router.post("/refresh")
def refresh_tokens(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Rotate tokens: validate the refresh token, enforce hard limit,
    revoke the old refresh token, and issue a fresh pair."""
    old_refresh = request.cookies.get(REFRESH_COOKIE_NAME)
    if not old_refresh:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token",
        )

    db_token = refresh_crud.get_refresh_token(db, old_refresh)
    if db_token is None:
        # Token revoked, expired, or never existed → force re-login
        _clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # ── Hard limit check ──────────────────────────────────────────
    now = datetime.now(timezone.utc)
    login_time = db_token.login_time
    # Ensure login_time is timezone-aware for comparison
    if login_time.tzinfo is None:
        login_time = login_time.replace(tzinfo=timezone.utc)

    if now - login_time > timedelta(hours=HARD_LIMIT_HOURS):
        # Absolute session limit reached → revoke everything
        refresh_crud.revoke_all_user_tokens(db, db_token.user_id)
        _clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please log in again.",
        )

    # ── Token rotation ────────────────────────────────────────────
    # Revoke old refresh token
    refresh_crud.revoke_refresh_token(db, old_refresh)

    # Look up the user for the new access token
    user = crud.get_user(db, user_id=db_token.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # New access token
    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    # New refresh token — inherits the original login_time for hard limit
    new_refresh = generate_refresh_token()
    refresh_crud.create_refresh_token(
        db=db,
        user_id=user.id,
        token=new_refresh,
        expires_at=now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        login_time=db_token.login_time,  # Preserve original login time
    )

    _set_auth_cookies(response, access_token, new_refresh)
    return {"message": "Tokens refreshed"}


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Logout: revoke ALL refresh tokens for the user, clear cookies."""
    # Try to identify the user from the access token to revoke all sessions
    token = request.cookies.get(COOKIE_NAME)
    if token:
        payload = decode_access_token(token)
        if payload:
            email = payload.get("sub")
            if email:
                user = crud.get_user_by_email(db, email=email)
                if user:
                    refresh_crud.revoke_all_user_tokens(db, user.id)

    # Also try to revoke the specific refresh token even if access token is expired
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if refresh_token:
        refresh_crud.revoke_refresh_token(db, refresh_token)

    _clear_auth_cookies(response)
    return {"message": "Successfully logged out"}


@router.post("/ws-ticket")
def get_ws_ticket(
    current_user: schemas.UserResponse = Depends(get_current_user)
):
    """Generate a short-lived ticket for WebSocket authentication."""
    import models
    ticket = str(uuid.uuid4())
    ws_tickets[ticket] = {
        "user_id": current_user.id,
        "expires": time.time() + TICKET_EXPIRY_SECONDS
    }
    return {"ticket": ticket}

@router.get("/me", response_model=schemas.UserResponse)
def read_users_me(current_user: schemas.UserResponse = Depends(get_current_user)):
    """API endpoint to get the current authenticated user details."""
    return current_user

@router.patch("/profile", response_model=schemas.UserResponse)
def update_profile(
    user_update: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: schemas.UserResponse = Depends(get_current_user)
):
    """API endpoint to update the current user's profile information."""
    updated_user = crud.update_user(db, current_user.id, user_update)
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return updated_user
