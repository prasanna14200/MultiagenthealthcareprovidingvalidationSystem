# add_test_data.py
import sqlite3
import os

DB_PATH = "data/providers.db"

# Ensure data directory exists
os.makedirs("data", exist_ok=True)

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# First, let's check what columns actually exist
cur.execute("PRAGMA table_info(providers)")
columns = cur.fetchall()
print("Existing columns in providers table:")
for col in columns:
    print(f"  - {col[1]} ({col[2]})")

# ✅ FIXED: Only use columns that ACTUALLY exist in your table
test_providers = [
    (1, "Dr. Sarah Johnson", "Dermatology", "123 Main St, City", "555-0101", "sarah.j@clinic.com", 0.95),
    (2, "Dr. Mike Chen", "Cardiology", "456 Oak Ave, Town", "555-0102", "mike.c@hospital.com", 0.88),
    (3, "Dr. Emily White", "Dermatology", "789 Pine Rd, Village", "555-0103", "emily.w@medcenter.com", 0.75),
    (4, "Dr. John Smith", "Orthopedics", "321 Elm St, City", "555-0104", "john.s@ortho.com", 0.92),
    (5, "Dr. Lisa Brown", "Dermatology", "654 Maple Dr, Town", "555-0105", "lisa.b@skin.com", 0.50),
]

# ✅ Only insert into columns that exist: id, name, specialty, address, phone, email, confidence
cur.executemany("""
    INSERT OR REPLACE INTO providers 
    (id, name, specialty, address, phone, email, confidence)
    VALUES (?, ?, ?, ?, ?, ?, ?)
""", test_providers)

conn.commit()

# Verify the da