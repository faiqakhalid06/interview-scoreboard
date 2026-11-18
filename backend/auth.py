import hashlib, hmac, os, secrets
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
from database import get_db
from models import User

bearer = HTTPBearer()
sessions = {}  # token -> user_id (cleared when the server restarts)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return salt.hex() + ":" + h.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, h_hex = stored.split(":")
    except ValueError:
        return False
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 100_000)
    return hmac.compare_digest(h.hex(), h_hex)


def create_token(user_id: int) -> str:
    token = secrets.token_hex(16)
    sessions[token] = user_id
    return token


def get_current_user(creds=Depends(bearer), db=Depends(get_db)):
    user_id = sessions.get(creds.credentials)
    user = db.get(User, user_id) if user_id else None
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    return user


def require_admin(user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user