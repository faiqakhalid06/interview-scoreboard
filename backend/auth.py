import base64
import hashlib
import hmac
import os
import time

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

from database import get_db
from models import User

bearer = HTTPBearer()

# Set SECRET_KEY as an environment variable when you deploy.
SECRET = os.environ.get("SECRET_KEY", "dev-secret-change-me")
TOKEN_HOURS = 12

if os.environ.get("DATABASE_URL") and SECRET == "dev-secret-change-me":
    raise RuntimeError("Set the SECRET_KEY environment variable before deploying.")


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


def _sign(payload: str) -> str:
    return hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def create_token(user_id: int) -> str:
    payload = f"{user_id}:{int(time.time()) + TOKEN_HOURS * 3600}"
    return base64.urlsafe_b64encode(f"{payload}:{_sign(payload)}".encode()).decode()


def read_token(token: str):
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        uid, exp, sig = raw.split(":")
        if hmac.compare_digest(sig, _sign(f"{uid}:{exp}")) and int(exp) > time.time():
            return int(uid)
    except Exception:
        pass
    return None


def get_current_user(creds=Depends(bearer), db=Depends(get_db)):
    user_id = read_token(creds.credentials)
    user = db.get(User, user_id) if user_id else None
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    return user


def require_admin(user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user