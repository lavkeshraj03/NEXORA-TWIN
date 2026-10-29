"""Exercise the running Next.js -> FastAPI -> PostgreSQL stack, then remove only its test records."""
import json
import secrets
from http.cookiejar import CookieJar
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.db.session import get_engine
from app.models import AuditLog, Business, Membership, User

BASE = "http://localhost:3000"


class RedirectMetadata(HTMLParser):
    """Next.js may redirect after its root loading boundary has begun streaming."""
    login_redirect = False

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "meta" and attrs.get("http-equiv", "").lower() == "refresh":
            self.login_redirect = attrs.get("content", "").split("url=", 1)[-1] == "/login"


def main():
    prefix = "nexora-http-" + uuid4().hex
    users: list[UUID] = []
    businesses: list[UUID] = []
    jars = [CookieJar(), CookieJar()]
    clients = [build_opener(HTTPCookieProcessor(jar)) for jar in jars]

    def call(index, path, method="GET", body=None, csrf=None, expected=200):
        headers = {"Origin": BASE}
        if csrf:
            headers["X-CSRF-Token"] = csrf
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = Request(BASE + "/api/backend/" + path, method=method, headers=headers, data=json.dumps(body).encode() if body is not None else None)
        try:
            response = clients[index].open(request, timeout=20)
        except HTTPError as failure:
            response = failure
        with response:
            raw = response.read()
            assert response.code == expected, f"{method} {path}: expected {expected}, got {response.code}"
            return json.loads(raw) if raw else None

    try:
        with clients[0].open(BASE + "/workspace", timeout=20) as response:
            page = response.read().decode()
            metadata = RedirectMetadata()
            metadata.feed(page)
            assert response.geturl().endswith("/login") or metadata.login_redirect, "Anonymous workspace did not redirect"
            assert "YOUR CONNECTED BUSINESS" not in page, "Anonymous response rendered the workspace"
        accounts = []
        for index in range(2):
            result = call(index, "auth/register", "POST", {"name":"HTTP Check", "email":f"{prefix}-{index}@example.com", "password":secrets.token_urlsafe(32)}, expected=201)
            users.append(UUID(result["user"]["id"]))
            accounts.append(result)
        first_csrf, second_csrf = [account["csrf_token"] for account in accounts]
        payload = {"name":"HTTP test workspace", "business_type":"retail", "country":"IN", "currency":"INR", "timezone":"Asia/Kolkata"}
        for name in ["HTTP retail test", "HTTP restaurant test"]:
            result = call(0, "businesses", "POST", payload | {"name":name}, first_csrf, 201)
            businesses.append(UUID(result["id"]))
        assert len(call(0, "businesses")) == 2
        assert call(1, "businesses") == []
        first_path, second_path = ["businesses/" + str(item) for item in businesses]
        call(1, first_path, expected=404)
        call(0, "businesses", "POST", payload, expected=403)
        call(0, first_path + "/members", "POST", {"email":accounts[1]["user"]["email"], "role":"viewer"}, first_csrf, 201)
        assert call(1, first_path)["role"] == "viewer"
        call(1, second_path, expected=404)
        call(1, first_path, "PUT", payload, second_csrf, 403)
        assert call(0, first_path + "/audit-logs")
        with clients[0].open(BASE + "/workspace", timeout=20) as response:
            assert response.geturl().endswith("/workspace")
            assert "HTTP Check" in response.read().decode()
        call(0, "auth/logout", "POST", csrf=first_csrf, expected=204)
        call(0, "auth/me", expected=401)
        print("HTTP checks passed: server-side protection, registration, cookie proxy, two businesses, tenant isolation, CSRF, viewer permissions, audit history, logout.")
    finally:
        # Never truncate tables or delete by a broad test-name pattern.
        with Session(get_engine()) as db:
            owned_users = db.scalars(select(User).where(User.id.in_(users))).all()
            assert all(user.email.startswith(prefix + "-") for user in owned_users)
            owned_businesses = db.scalars(select(Membership.business_id).where(Membership.business_id.in_(businesses), Membership.user_id.in_(users), Membership.role == "owner")).all()
            assert set(owned_businesses) == set(businesses), "Could not verify cleanup ownership"
            db.execute(delete(AuditLog).where(AuditLog.user_id.in_(users)))
            db.execute(delete(Business).where(Business.id.in_(businesses)))
            db.execute(delete(User).where(User.id.in_(users)))
            db.commit()
        print("Removed the HTTP check's temporary accounts and workspaces.")


if __name__ == "__main__":
    main()
