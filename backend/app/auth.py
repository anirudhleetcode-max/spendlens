from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from pymongo.errors import DuplicateKeyError

from .db import get_db
from .security import create_token, current_user, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


def public_user(u: dict) -> dict:
    return {"id": str(u["_id"]), "name": u["name"], "email": u["email"]}


@router.post("/register", status_code=201)
async def register(body: RegisterIn):
    doc = {
        "name": body.name.strip(),
        "email": body.email.lower(),
        "password_hash": hash_password(body.password),
        "created_at": datetime.now(timezone.utc),
    }
    try:
        res = await get_db().users.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "An account with this email already exists")
    doc["_id"] = res.inserted_id
    return {"token": create_token(str(res.inserted_id)), "user": public_user(doc)}


@router.post("/login")
async def login(body: LoginIn):
    u = await get_db().users.find_one({"email": body.email.lower()})
    if not u or not verify_password(body.password, u["password_hash"]):
        raise HTTPException(401, "Incorrect email or password")
    return {"token": create_token(str(u["_id"])), "user": public_user(u)}


@router.get("/me")
async def me(user: dict = Depends(current_user)):
    return public_user(user)
