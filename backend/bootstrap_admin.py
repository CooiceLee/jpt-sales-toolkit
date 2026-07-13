"""
Bootstrap first admin account.

Usage:
    python -m backend.bootstrap_admin

Creates the first leader account if no users exist.
"""

from __future__ import annotations

import hashlib
import secrets
import sys
from pathlib import Path

from .config import init_settings
from .repositories import init_db, UserRepository


def hash_password(password: str) -> str:
    """Hash password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def generate_password(length: int = 12) -> str:
    """Generate a random password."""
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def bootstrap():
    """Create first admin account if none exists."""
    # Initialize
    app_root = Path(__file__).parent.parent
    settings = init_settings(app_root)
    init_db(settings.db_path)

    # Check existing users
    user_repo = UserRepository()
    existing = user_repo.list_all()

    if existing:
        print(f"Database already has {len(existing)} user(s).")
        print("Bootstrap aborted - only runs on empty database.")
        return False

    # Get admin info
    print("\n=== JPT Sales Toolkit - First Admin Setup ===\n")

    username = input("Admin username [admin]: ").strip() or "admin"
    display_name = input("Display name [Administrator]: ").strip() or "Administrator"

    use_generated = input("Generate random password? [Y/n]: ").strip().lower()
    if use_generated in ("", "y", "yes"):
        password = generate_password()
        print(f"\nGenerated password: {password}")
        print("Please save this password securely!")
    else:
        password = input("Enter password: ").strip()
        if len(password) < 6:
            print("Error: Password must be at least 6 characters")
            return False

    # Create admin user
    user_id = user_repo.create(
        username=username,
        password_hash=hash_password(password),
        display_name=display_name,
        role="leader",
        region=None,
    )

    print(f"\n✓ Admin account created successfully!")
    print(f"  User ID: {user_id}")
    print(f"  Username: {username}")
    print(f"  Role: leader")
    print(f"\nYou can now login at: POST /api/auth/login")
    print(f"  Body: {{'username': '{username}', 'password': '...'}}")

    return True


def main():
    try:
        success = bootstrap()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nAborted.")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
