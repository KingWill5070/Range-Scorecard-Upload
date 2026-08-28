# ============================================================
# SECTION 1 — IMPORTS + SETTINGS
# ============================================================

from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta

# -------------------------
# Security Settings
# -------------------------
SECRET_KEY = "SUPER_SECRET_KEY_CHANGE_THIS"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# ============================================================
# SECTION 2 — PASSWORD HASHING + VERIFICATION
# ============================================================

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)
# ============================================================
# SECTION 3 — JWT CREATION
# ============================================================

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
# ============================================================
# SECTION 4 — JWT DECODING
# ============================================================

def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
