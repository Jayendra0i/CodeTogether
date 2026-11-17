
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session, sessionmaker
from passlib.context import CryptContext
from jose import jwt, JWTError
from google.oauth2 import id_token
from google.auth.transport import requests
from types import SimpleNamespace

from backend.database import engine
from backend.models import User


from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH, override=False)


SECRET_KEY = os.getenv("SECRET_KEY")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY missing in backend/.env")


# Database session
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)


# JWT security
security = HTTPBearer()
router = APIRouter(prefix="/auth", tags=["Authentication"])


# =========================
# REQUEST MODELS
# =========================

class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleLoginRequest(BaseModel):
    credential: str


# =========================
# HELPER FUNCTIONS
# =========================

def hash_password(password: str):
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: int):
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": str(user_id),
        "exp": expire
    }

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def user_response(user: User):
    return {
        "id": user.id,
        "name": user.username,
        "email": user.email
    }


def create_login_response(user: User):
    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "user": user_response(user)
    }


# =========================
# CURRENT USER
# =========================

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False)),
    db: Session = Depends(get_db)
):
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        user_id = payload.get("sub")

        if payload.get("guest"):
            return SimpleNamespace(
                id=None,
                username=payload.get("name", "Guest"),
                email=payload.get("email", ""),
                is_active=True,
                guest=True,
                room_code=payload.get("room_code", ""),
            )

        if user_id is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid authentication token"
            )

    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )

    user = db.query(User).filter(
        User.id == int(user_id)
    ).first()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="User not found or inactive"
        )

    return user


# =========================
# REGISTER
# =========================

@router.post("/register")
def register(
    data: RegisterRequest,
    db: Session = Depends(get_db)
):
    email = data.email.lower().strip()
    username = data.name.strip()

    if db.query(User).filter(User.email == email).first():
        raise HTTPException(
            status_code=409,
            detail="Email is already registered"
        )

    if db.query(User).filter(User.username == username).first():
        raise HTTPException(
            status_code=409,
            detail="Username is already taken"
        )

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(data.password),
        auth_provider="email",
        is_active=True
    )

    try:
        db.add(user)
        db.commit()
        db.refresh(user)

        return create_login_response(user)

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to create account"
        )


# =========================
# LOGIN
# =========================

@router.post("/login")
def login(
    data: LoginRequest,
    db: Session = Depends(get_db)
):
    email = data.email.lower().strip()

    user = db.query(User).filter(
        User.email == email
    ).first()

    if (
        not user
        or not user.password_hash
        or not verify_password(data.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Your account is inactive"
        )

    return create_login_response(user)


# =========================
# GOOGLE LOGIN
# =========================

@router.post("/google")
def google_login(
    data: GoogleLoginRequest,
    db: Session = Depends(get_db)
):
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=500,
            detail="Google Login is not configured"
        )

    try:
        google_user = id_token.verify_oauth2_token(
            data.credential,
            requests.Request(),
            GOOGLE_CLIENT_ID
        )

        email = google_user.get("email", "").lower().strip()
        google_id = google_user.get("sub")
        name = google_user.get("name") or email.split("@")[0]

        if not email or not google_id or not google_user.get("email_verified"):
            raise HTTPException(
                status_code=401,
                detail="Google account email is not verified"
            )

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Google authentication failed"
        )

    user = db.query(User).filter(
        User.google_id == google_id
    ).first()

    if not user:
        user = db.query(User).filter(
            User.email == email
        ).first()

        if user:
            if user.google_id and user.google_id != google_id:
                raise HTTPException(
                    status_code=409,
                    detail="This email is linked to another Google account"
                )

            user.google_id = google_id
            user.auth_provider = "google"

        else:
            username = name[:100]
            base_username = username
            counter = 1

            while db.query(User).filter(
                User.username == username
            ).first():
                suffix = str(counter)
                username = base_username[:100 - len(suffix)] + suffix
                counter += 1

            user = User(
                username=username,
                email=email,
                google_id=google_id,
                auth_provider="google",
                is_active=True
            )

            db.add(user)

        try:
            db.commit()
            db.refresh(user)
        except Exception:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail="Unable to create Google account"
            )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Your account is inactive"
        )

    return create_login_response(user)


# =========================
# GET LOGGED-IN USER
# =========================

@router.get("/me")
def get_me(
    current_user: User = Depends(get_current_user)
):
    return user_response(current_user)
