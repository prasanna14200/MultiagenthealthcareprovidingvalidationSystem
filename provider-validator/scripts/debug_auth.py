import os
import sys
sys.path.insert(0, os.path.abspath('.'))

from dotenv import load_dotenv
load_dotenv()
SECRET_KEY=os.getenv('SECRET_KEY')
print("=" * 60)
print("🔍 AUTHENTICATION DEBUG")
print("=" * 60)

# Check 1: Environment Variables
print("\n1️⃣ Environment Variables:")
print(f"   SECRET_KEY: {os.getenv('SECRET_KEY', 'NOT FOUND')[:30]}...")
print(f"   USER_DB_PATH: {os.getenv('USER_DB_PATH', 'NOT FOUND')}")
print(f"   ALGORITHM: {os.getenv('ALGORITHM', 'NOT FOUND')}")

# Check 2: Database exists
import sqlite3
user_db = os.getenv('USER_DB_PATH', 'data/users.db')
print(f"\n2️⃣ User Database Check:")
print(f"   Path: {user_db}")
print(f"   Exists: {os.path.exists(user_db)}")

if os.path.exists(user_db):
    conn = sqlite3.connect(user_db)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if cur.fetchone():
        print(f"   ✅ Table 'users' exists")
        cur.execute("SELECT username, role FROM users")
        users = cur.fetchall()
        print(f"   Users in DB: {users}")
    else:
        print(f"   ❌ Table 'users' does NOT exist")
    conn.close()
else:
    print(f"   ❌ Database file not found!")

# Check 3: Test password hashing
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

test_password = "admin123"
print(f"\n3️⃣ Password Hashing Test:")
try:
    hashed = pwd_context.hash(test_password)
    print(f"   ✅ Hash created: {hashed[:30]}...")
    verified = pwd_context.verify(test_password, hashed)
    print(f"   ✅ Verification: {verified}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Check 4: Test JWT token creation
from jose import jwt
from datetime import datetime, timedelta

secret = os.getenv('SECRET_KEY')
algo = os.getenv('ALGORITHM', 'HS256')

print(f"\n4️⃣ JWT Token Test:")
try:
    test_data = {"sub": "admin", "role": "admin", "exp": datetime.utcnow() + timedelta(minutes=30)}
    token = jwt.encode(test_data, secret, algorithm=algo)
    print(f"   ✅ Token created: {token[:50]}...")
    
    # Try to decode it back
    decoded = jwt.decode(token, secret, algorithms=[algo])
    print(f"   ✅ Token decoded: {decoded}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Check 5: Test actual authentication
print(f"\n5️⃣ Authentication Test:")
if os.path.exists(user_db):
    from src.auth import authenticate_user, create_access_token
    
    user = authenticate_user("admin", "admin123")
    if user:
        print(f"   ✅ User authenticated: {user.username} (role: {user.role})")
        token = create_access_token(data={"sub": user.username, "role": user.role})
        print(f"   ✅ Token generated: {token[:50]}...")
    else:
        print(f"   ❌ Authentication FAILED")

print("\n" + "=" * 60)