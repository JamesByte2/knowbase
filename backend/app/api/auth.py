from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.security import create_token, decode_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)


class AuthIn(BaseModel):
    email: EmailStr
    password: str


def current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if cred is None:
        raise HTTPException(401, "未登录")
    user_id = decode_token(cred.credentials)
    if user_id is None:
        raise HTTPException(401, "登录已过期")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(401, "用户不存在")
    return user


@router.post("/register")
def register(body: AuthIn, db: Session = Depends(get_db)):
    if len(body.password) < 8:
        raise HTTPException(400, "密码至少 8 位")
    exists = db.scalar(select(User).where(User.email == body.email))
    if exists:
        raise HTTPException(400, "该邮箱已注册")
    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return {"token": create_token(user.id)}


@router.post("/login")
def login(body: AuthIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "邮箱或密码错误")
    return {"token": create_token(user.id)}
