"""Run against PostgreSQL/Redis; all database changes roll back after each test."""
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import COOKIE, rate_limit, token_digest
from app.db.session import get_engine, get_session
from app.main import create_app
from app.models import AuthSession, User

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="Requires migrated PostgreSQL and Redis")]
PASSWORD = "a correct horse battery staple"
ORIGIN = {"Origin": "http://localhost:3000"}
DATA = {"name": "NovaMart", "business_type": "retail", "country": "IN", "currency": "INR", "timezone": "Asia/Kolkata"}


@pytest.fixture
def accounts():
    connection = get_engine().connect()
    transaction = connection.begin()
    app = create_app()
    def session_override():
        with Session(connection, expire_on_commit=False, join_transaction_mode="create_savepoint") as session:
            yield session
    app.dependency_overrides[get_session] = session_override
    prefix = uuid4().hex
    with TestClient(app, client=("owner-" + prefix, 50000)) as owner, TestClient(app, client=("other-" + prefix, 50001)) as other:
        one = owner.post("/api/v1/auth/register", headers=ORIGIN, json={"name":"Owner", "email":prefix+"@example.com", "password":PASSWORD})
        two = other.post("/api/v1/auth/register", headers=ORIGIN, json={"name":"Other", "email":prefix+"other@example.com", "password":PASSWORD})
        assert one.status_code == 201, one.text
        assert two.status_code == 201, two.text
        yield owner, other, ORIGIN | {"X-CSRF-Token":one.json()["csrf_token"]}, ORIGIN | {"X-CSRF-Token":two.json()["csrf_token"]}, one.json(), two.json(), connection
    transaction.rollback()
    connection.close()


def create(client, headers, **changes):
    response = client.post("/api/v1/businesses", headers=headers, json=DATA | changes)
    assert response.status_code == 201, response.text
    return response.json()


def test_login_logout_and_session_replay(accounts):
    owner, _, headers, _, one, _, _ = accounts
    assert owner.get("/api/v1/auth/me").json()["user"]["id"] == one["user"]["id"]
    original = owner.cookies.get(COOKIE)
    assert owner.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert owner.get("/api/v1/auth/me", headers={"Cookie":f"{COOKIE}={original}"}).status_code == 401
    credentials = {"email":one["user"]["email"], "password":PASSWORD}
    assert owner.post("/api/v1/auth/login", json=credentials, headers=ORIGIN).status_code == 200
    assert owner.cookies.get(COOKIE) != original
    assert owner.post("/api/v1/auth/login", json=credentials | {"password":"wrong password here"}, headers=ORIGIN).status_code == 401


def test_origin_csrf_and_cookie_flags(accounts, monkeypatch):
    owner, _, headers, _, one, _, _ = accounts
    assert owner.post("/api/v1/businesses", headers=ORIGIN, json=DATA).status_code == 403
    assert owner.post("/api/v1/businesses", headers=headers | {"Origin":"https://attacker.example"}, json=DATA).status_code == 403
    credentials = {"email":one["user"]["email"], "password":PASSWORD}
    assert owner.post("/api/v1/auth/login", json=credentials).status_code == 403
    response = owner.post("/api/v1/auth/login", headers=ORIGIN, json=credentials)
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=lax" in response.headers["set-cookie"].lower()
    assert "password" not in response.json()["user"]
    monkeypatch.setattr(get_settings(), "environment", "production")
    secure = owner.post("/api/v1/auth/login", headers=ORIGIN, json=credentials)
    assert secure.status_code == 200
    assert "secure" in secure.headers["set-cookie"].lower()


def test_malformed_non_ascii_csrf_is_rejected(accounts):
    owner = accounts[0]
    response = owner.post("/api/v1/businesses", headers=[(b"origin", b"http://localhost:3000"), (b"x-csrf-token", b"\xff")], json=DATA)
    assert response.status_code == 403


def test_two_businesses_switch_and_isolation(accounts):
    owner, other, headers, other_headers, _, _, _ = accounts
    one = create(owner, headers)
    two = create(owner, headers, name="FoodSphere", business_type="restaurant", currency="USD", timezone="America/New_York", country="US")
    assert {b["id"] for b in owner.get("/api/v1/businesses").json()} == {one["id"],two["id"]}
    for business in [one,two,one]:
        assert owner.get(f"/api/v1/businesses/{business['id']}").json()["currency"] == business["currency"]
    assert other.get("/api/v1/businesses").json() == []
    for suffix in ["", "/members", "/audit-logs"]:
        assert other.get(f"/api/v1/businesses/{one['id']}{suffix}").status_code == 404
    assert other.put(f"/api/v1/businesses/{one['id']}", headers=other_headers, json=DATA).status_code == 404
    assert other.post(f"/api/v1/businesses/{one['id']}/members", headers=other_headers, json={"email":"owner@example.com","role":"owner"}).status_code == 404
    update = owner.put(f"/api/v1/businesses/{one['id']}", headers=headers, json=DATA | {"name":"Updated","currency":"EUR"})
    assert update.status_code == 200
    assert owner.get(f"/api/v1/businesses/{two['id']}").json()["currency"] == "USD"
    assert all(event["target_id"] != two["id"] for event in owner.get(f"/api/v1/businesses/{one['id']}/audit-logs").json())


def test_viewer_cannot_write_or_escalate(accounts):
    owner, other, headers, other_headers, _, two, _ = accounts
    business = create(owner, headers)
    path = f"/api/v1/businesses/{business['id']}"
    added = owner.post(path+"/members", headers=headers, json={"email":two["user"]["email"],"role":"viewer"})
    assert added.status_code == 201
    assert other.get(path).json()["role"] == "viewer"
    assert other.put(path, headers=other_headers, json=DATA).status_code == 403
    assert other.get(path+"/members").status_code == 403
    assert other.get(path+"/audit-logs").status_code == 403
    assert other.patch(path+f"/members/{two['user']['id']}", headers=other_headers, json={"role":"owner"}).status_code == 403


def test_admin_limits_owner_retention_and_revocation(accounts):
    owner, other, headers, other_headers, one, two, _ = accounts
    business = create(owner, headers)
    path = f"/api/v1/businesses/{business['id']}"
    assert owner.post(path+"/members", headers=headers, json={"email":two["user"]["email"],"role":"administrator"}).status_code == 201
    assert other.patch(path+f"/members/{one['user']['id']}", headers=other_headers, json={"role":"viewer"}).status_code == 403
    assert other.patch(path+f"/members/{two['user']['id']}", headers=other_headers, json={"role":"owner"}).status_code == 403
    assert owner.delete(path+f"/members/{one['user']['id']}", headers=headers).status_code == 409
    assert owner.patch(path+f"/members/{one['user']['id']}", headers=headers, json={"role":"viewer"}).status_code == 409
    assert owner.delete(path+f"/members/{two['user']['id']}", headers=headers).status_code == 204
    assert other.get(path).status_code == 404


def test_expired_session_and_platform_flag_do_not_bypass_tenancy(accounts):
    owner, other, headers, _, _, two, connection = accounts
    business = create(owner, headers)
    with Session(connection, join_transaction_mode="create_savepoint") as db:
        user = db.get(User, two["user"]["id"])
        user.is_platform_admin = True
        db.commit()
    assert other.get(f"/api/v1/businesses/{business['id']}").status_code == 404
    with Session(connection, join_transaction_mode="create_savepoint") as db:
        session = db.get(AuthSession, token_digest(owner.cookies.get(COOKIE)))
        session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert owner.get("/api/v1/auth/me").status_code == 401


def test_schema_validation_and_duplicate_email(accounts):
    owner, _, headers, _, one, _, _ = accounts
    for change in [{"timezone":"invalid/timezone"}, {"reporting_month":0}, {"modules":["ingredients"]}, {"is_platform_admin":True}]:
        assert owner.post("/api/v1/businesses", headers=headers, json=DATA | change).status_code == 422
    duplicate = owner.post("/api/v1/auth/register", headers=ORIGIN, json={"name":"Duplicate", "email":one["user"]["email"].upper(), "password":PASSWORD})
    assert duplicate.status_code == 409


def test_real_redis_rate_limit():
    key = "integration-test:" + uuid4().hex
    try:
        rate_limit(key, 1, 60)
        with pytest.raises(HTTPException) as exc:
            rate_limit(key, 1, 60)
        assert exc.value.status_code == 429
    finally:
        with Redis.from_url(get_settings().redis_url.get_secret_value()) as redis:
            redis.delete("nexora:auth:" + token_digest(key))
