from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, WebSocket
from sqlalchemy.orm import Session
from datetime import timedelta
import os

from database import get_db
import schemas.user as schemas
import crud.user as crud
from utils.auth import (
    verify_password, 
    create_access_token, 
    decode_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

COOKIE_NAME = "access_token"
IS_PRODUCTION = os.getenv("ENVIRONMENT", "development") == "production"

# In-memory storage for short-lived WebSocket tickets
# Format: { ticket_uuid: {"user_id": int, "expires": float} }
import uuid
import time
ws_tickets = {}
TICKET_EXPIRY_SECONDS = 60

from typing import Union

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
    """API endpoint to login and receive an HttpOnly cookie."""
    user = crud.get_user_by_email(db, email=credentials.email)
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Cookie"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    
    # Set HttpOnly Cookie
    response.set_cookie(
        key=COOKIE_NAME,
        value=access_token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        expires=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax" if not IS_PRODUCTION else "none",
        secure=IS_PRODUCTION, # Set to True in production (requires HTTPS)
        path="/"
    )
    
    return {
        "message": "Successfully logged in", 
        "user": {
            "email": user.email,
            "full_name": user.full_name,
            "id": user.id,
            "university": user.university
        }
    }

@router.post("/logout")
def logout(response: Response):
    """API endpoint to logout by clearing the HttpOnly cookie."""
    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=True,
        samesite="lax" if not IS_PRODUCTION else "none",
        secure=IS_PRODUCTION,
        path="/"
    )
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
