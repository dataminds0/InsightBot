"""Authentication endpoints: register, login, logout, me."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from insightbot.api.deps import get_auth_service, get_current_user
from insightbot.models.user import User
from insightbot.services.auth_service import AuthenticationError, AuthService

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8)
    email: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    user_id: str
    username: str
    email: Optional[str]
    role: str
    status: str


class LoginResponse(BaseModel):
    user: UserResponse
    token: str


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    req: RegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    """Self-registration endpoint. New users are placed in pending status awaiting administrator approval."""
    try:
        user = auth_service.register(
            username=req.username,
            password=req.password,
            email=req.email,
        )
        return {
            "user_id": user.user_id,
            "username": user.username,
            "status": user.status.value,
            "message": "Registration submitted successfully. Awaiting administrator approval.",
        }
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/login", response_model=LoginResponse)
def login(
    req: LoginRequest,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    """Authenticate credentials and establish session."""
    try:
        user, session = auth_service.login(username=req.username, password=req.password)
        # Set HttpOnly session cookie
        response.set_cookie(
            key="insightbot_session",
            value=session.session_token,
            httponly=True,
            samesite="lax",
            secure=False,  # Can be True in HTTPS production
        )
        return LoginResponse(
            user=UserResponse(
                user_id=user.user_id,
                username=user.username,
                email=user.email,
                role=user.role.value,
                status=user.status.value,
            ),
            token=session.session_token,
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))


@router.post("/logout")
def logout(
    response: Response,
    user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    """Terminate current user session."""
    response.delete_cookie(key="insightbot_session")
    return {"message": "Logged out successfully."}


@router.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(get_current_user)) -> UserResponse:
    """Return profile and permissions for currently authenticated user."""
    return UserResponse(
        user_id=user.user_id,
        username=user.username,
        email=user.email,
        role=user.role.value,
        status=user.status.value,
    )
