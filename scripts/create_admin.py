"""Provision a platform account; this grants no implicit tenant memberships."""
import argparse
from getpass import getpass
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import get_engine
from app.models import User
from app.schemas import Register


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    password = getpass("Password (12–128 characters): ")
    if password != getpass("Confirm password: "):
        parser.error("Passwords do not match")
    data = Register(email=args.email, name=args.name, password=password)
    with Session(get_engine()) as db:
        user = User(email=data.email, name=data.name, password_hash=hash_password(data.password), is_platform_admin=True)
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            parser.error("An account with this email already exists")
        print(f"Created platform account {user.id}. Tenant membership must be explicitly granted.")


if __name__ == "__main__":
    main()
