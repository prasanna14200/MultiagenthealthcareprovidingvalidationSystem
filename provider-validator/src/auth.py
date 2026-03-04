# src/auth.py
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status, APIRouter
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
import sqlite3
from dotenv import load_dotenv

load_dotenv()

# Config
SECRET_KEY=os.getenv("SECRET_KEY", "default-secret-key-change-in-production")
ALGORITHM=os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
router = APIRouter()

USER_DB_PATH = os.getenv("USER_DB_PATH", "data/users.db")

# Pydantic models
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None

class UserInDB(BaseModel):
    username: str
    hashed_password: str
    role: str
    disabled: bool = False

# --- DB helpers (simple sqlite helpers)
def get_db_conn():
    return sqlite3.connect(USER_DB_PATH)

def get_user_from_db(username: str) -> Optional[UserInDB]:
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, hashed_password TEXT NOT NULL, role TEXT NOT NULL, disabled INTEGER DEFAULT 0)""")
    cur.execute("""SELECT username, hashed_password, role, disabled FROM users WHERE username = ?""", (username,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return UserInDB(username=row[0], hashed_password=row[1], role=row[2], disabled=bool(row[3]))

def create_user_db(username: str, password: str, role: str = "reviewer"):
    """Create a new user in the database"""
    # ✅ FIX 4: Limit password length to 72 bytes for bcrypt
    if len(password) > 72:
        password = password[:72]
    hashed = pwd_context.hash(password)
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, hashed_password TEXT NOT NULL, role TEXT NOT NULL, disabled INTEGER DEFAULT 0)")
    try:
        cur.execute("INSERT INTO users (username, hashed_password, role) VALUES (?, ?, ?)",
                    (username, hashed, role))
        conn.commit()
    except Exception as e:
        conn.close()
        raise
    conn.close()

# --- Auth helpers
def verify_password(plain_password, hashed_password):
    """Verify plain password against hashed password"""
    try:
        # ✅ FIX 5: Truncate password to 72 bytes for bcrypt validation
        if len(plain_password) > 72:
            plain_password = plain_password[:72]
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        print(f"❌ Password verification error: {e}")
        return False
  

def authenticate_user(username: str, password: str):
    user = get_user_from_db(username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] |None= None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# --- FastAPI dependencies
async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials (login required)",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role", "reviewer")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username, role=role)
    except JWTError:
        raise credentials_exception
    user = get_user_from_db(token_data.username)
    if user is None:
        raise credentials_exception
    if user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user

async def get_current_active_user(current_user: UserInDB = Depends(get_current_user)):
    # add additional active checks if you keep 'disabled' flag
    return current_user

# --- Token endpoint
@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
     
    
    print("Username received:", form_data.username)
    print("Password received:", form_data.password)

    user = authenticate_user(form_data.username, form_data.password)
    print("Auth result:", user)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            #headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}
