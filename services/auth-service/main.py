import os
import sys
sys.path.insert(0, "/app/shared")

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from observability import create_app, get_logger
from database import get_db, init_db
from models import User

log = get_logger()

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))


@asynccontextmanager
async def lifespan(app):
    init_db()
    log.info("auth-service started")
    yield

app = create_app("Auth Service", lifespan=lifespan)


# ── Schemas ────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    password: str
    customer_id: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    customer_id: str | None = None


class ValidateRequest(BaseModel):
    token: str


# ── Helpers ────────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.post("/auth/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=req.email,
        password_hash=hash_password(req.password),
        customer_id=req.customer_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_token({"sub": user.email, "customer_id": user.customer_id})
    log.info("user registered", email=req.email, customer_id=req.customer_id)
    return TokenResponse(access_token=token, customer_id=user.customer_id)


@app.post("/auth/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.password_hash):
        log.warning("failed login attempt", email=form.username)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token({"sub": user.email, "customer_id": user.customer_id})
    log.info("user logged in", email=form.username)
    return TokenResponse(access_token=token, customer_id=user.customer_id)


@app.post("/auth/validate")
async def validate(req: ValidateRequest):
    try:
        payload = jwt.decode(req.token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return {"valid": True, "email": payload.get("sub"), "customer_id": payload.get("customer_id")}
    except jwt.PyJWTError as e:
        log.warning("token validation failed", error=str(e))
        raise HTTPException(status_code=401, detail="Invalid or expired token")
