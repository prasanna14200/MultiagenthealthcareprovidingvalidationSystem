# src/create_user.py
import getpass
import sys
from auth import create_user_db

def main():
    if len(sys.argv) >= 3:
        username = sys.argv[1]
        role = sys.argv[2]
        password = None
    else:
        username = input("Username: ").strip()
        role = input("Role (admin/reviewer) [reviewer]: ").strip() or "reviewer"
        password = getpass.getpass("Password: ")
    if not password:
        # interactive fallback
        password = getpass.getpass("Password: ")
    create_user_db(username, password, role)
    print(f"User {username} created with role {role}")

if __name__ == "__main__":
    main()
