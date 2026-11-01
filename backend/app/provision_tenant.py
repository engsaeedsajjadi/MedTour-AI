"""Controlled provisioning of a customer organization (tenant) and its first administrator.

Runs with the migration (owner) database connection, never from the public API:

    docker compose run --rm migrate python -m app.provision_tenant \\
        --slug clinic-a --name "Clinic A" --admin-email admin@clinic-a.example

The password is read without echo (or from stdin with --password-stdin) and never printed.
The new admin must enrol two-factor authentication at first sign-in when MFA is enforced.
"""
from __future__ import annotations
import argparse
import getpass
import re
import sys
from sqlalchemy import select
from .database import SessionLocal
from .models import Tenant, User, Audit
from . import enterprise_models  # noqa: F401  register tables
from .security import password_hash
from .tenant_context import bind_tenant

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$")
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,}$")


def validate_password(password: str) -> None:
    # Same minimum as every other staff password in the application.
    if len(password) < 16:
        raise ValueError("Password must contain at least 16 characters")
    classes = sum(bool(re.search(p, password)) for p in (r"[a-z]", r"[A-Z]", r"[0-9]", r"[^A-Za-z0-9]"))
    if classes < 3:
        raise ValueError("Password needs at least three of: lower case, upper case, digits, symbols")


def provision(slug: str, name: str, email: str, password: str) -> tuple[str, str]:
    slug = slug.strip().lower()
    email = email.strip().lower()
    if not SLUG.fullmatch(slug):
        raise ValueError("Slug: 3-50 lower-case letters, digits or hyphens")
    if not 2 <= len(name.strip()) <= 120:
        raise ValueError("Organization name must contain 2-120 characters")
    if not EMAIL.fullmatch(email):
        raise ValueError("Invalid administrator email")
    validate_password(password)
    with SessionLocal() as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == slug))
        if tenant is None:
            tenant = Tenant(slug=slug, name=name.strip())
            db.add(tenant)
            db.flush()
        bind_tenant(db, tenant.id)
        if db.scalar(select(User.id).where(User.tenant_id == tenant.id).limit(1)):
            raise ValueError("This organization already has users; manage further accounts from the admin panel")
        user = User(tenant_id=tenant.id, email=email, password_hash=password_hash(password), role="admin")
        db.add(user)
        db.flush()
        db.add(Audit(tenant_id=tenant.id, user_id=user.id, event="tenant_provisioned",
                     entity_type="Tenant", entity_id=tenant.id))
        db.commit()
        return tenant.id, user.id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create an organization and its first administrator")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--password-stdin", action="store_true", help="read the password from standard input")
    args = parser.parse_args(argv)
    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\n")
    else:
        password = getpass.getpass("New admin password: ")
        if password != getpass.getpass("Repeat password: "):
            print("Passwords do not match", file=sys.stderr)
            return 2
    try:
        provision(args.slug, args.name, args.admin_email, password)
    except ValueError as error:
        print(f"Refused: {error}", file=sys.stderr)
        return 2
    print(f"Organization '{args.slug.strip().lower()}' created with administrator {args.admin_email.strip().lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
