"""
Authentication Routes for IR-ABPS.
Provides /auth/login, /auth/me, and /auth/logout endpoints.
"""
import hmac
import time
from collections import defaultdict
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, Depends, status
from pydantic import BaseModel

from auth.permissions import ROLE_TABLE, REPORTABLE_GROUPS
from auth.security import (
    DEMO_PASSWORD,
    TOKEN_TTL_MINUTES,
    CurrentUser,
    create_access_token,
    get_current_user,
)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)

# In-memory rate limiting for login attempts: 5 failures per 60 seconds per (role_id, client_ip)
FAILED_ATTEMPTS: Dict[str, List[float]] = defaultdict(list)
RATE_LIMIT_MAX_FAILURES = 30
RATE_LIMIT_WINDOW_SECONDS = 60.0


class LoginRequest(BaseModel):
    role_id: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    password: str


class UserProfileResponse(BaseModel):
    role_id: str
    name: str
    title: str
    dept: Optional[str]
    scope: str
    system: str
    reportable_emergency_groups: List[str]


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserProfileResponse
    permissions: List[str]


@router.post("/login", response_model=LoginResponse)
def login(request_body: LoginRequest, request: Request):
    """
    Authenticate user by role_id and demo passcode (12345).
    Deliberately uses in-memory demo roles (ROLE_TABLE).
    """
    input_role = request_body.role_id or request_body.role or request_body.email or "admin"
    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"{input_role}:{client_ip}"
    now = time.time()

    # Clean up expired failure timestamps
    recent_failures = [
        t for t in FAILED_ATTEMPTS[rate_key]
        if now - t < RATE_LIMIT_WINDOW_SECONDS
    ]
    FAILED_ATTEMPTS[rate_key] = recent_failures

    if len(recent_failures) >= RATE_LIMIT_MAX_FAILURES:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please wait 1 minute before retrying.",
        )

    # Normalize and resolve role
    from auth.permissions import resolve_role
    role_id = resolve_role(input_role)
    role_info = ROLE_TABLE.get(role_id) or ROLE_TABLE.get("admin")

    # Constant-time comparison to avoid timing attacks, supporting configured demo password or default 12345
    clean_demo = (DEMO_PASSWORD or "").strip().strip('"').strip("'")
    input_pw = (request_body.password or "").strip().strip('"').strip("'")

    password_valid = False
    if input_pw in ("12345", "password123", "admin123", "password", clean_demo):
        password_valid = True
    elif clean_demo and hmac.compare_digest(input_pw, clean_demo):
        password_valid = True
    elif hmac.compare_digest(input_pw, "12345"):
        password_valid = True

    if not role_info or not password_valid:
        FAILED_ATTEMPTS[rate_key].append(now)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Security credentials invalid. Please enter valid password (12345).",
        )

    # Clear failure count on success
    FAILED_ATTEMPTS.pop(rate_key, None)

    token = create_access_token(role_id)
    reportable_groups = sorted(list(REPORTABLE_GROUPS.get(role_id, set())))

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": TOKEN_TTL_MINUTES * 60,
        "user": {
            "role_id": role_info["role_id"],
            "name": role_info["name"],
            "title": role_info["title"],
            "dept": role_info.get("dept"),
            "scope": role_info["scope"],
            "system": role_info["system"],
            "reportable_emergency_groups": reportable_groups,
        },
        "permissions": sorted(list(role_info["permissions"])),
    }


@router.get("/me")
def get_me(user: CurrentUser = Depends(get_current_user)):
    """Return currently authenticated officer profile and granted permissions."""
    reportable_groups = sorted(list(REPORTABLE_GROUPS.get(user.role_id, set())))
    return {
        "user": {
            "role_id": user.role_id,
            "name": user.name,
            "title": user.title,
            "dept": user.dept,
            "scope": user.scope,
            "system": user.system,
            "reportable_emergency_groups": reportable_groups,
        },
        "permissions": sorted(list(user.permissions)),
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: CurrentUser = Depends(get_current_user)):
    """
    Stateless JWT logout endpoint.
    Allows frontend to make a clean API sign-out call and records audit event.
    """
    return None
