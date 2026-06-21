"""
Tests for /auth/* endpoints routed through the gateway.
"""
import uuid
import requests
from conftest import GATEWAY, auth_header


class TestRegister:
    def test_register_success(self):
        uid = str(uuid.uuid4())[:8]
        r = requests.post(
            f"{GATEWAY}/auth/register",
            json={"username": f"newuser_{uid}", "password": "password123", "role": "farmer"},
        )
        assert r.status_code == 201
        assert "user_id" in r.json()

    def test_register_duplicate_username(self):
        uid = str(uuid.uuid4())[:8]
        payload = {"username": f"dup_{uid}", "password": "password123", "role": "farmer"}
        requests.post(f"{GATEWAY}/auth/register", json=payload)
        r = requests.post(f"{GATEWAY}/auth/register", json=payload)
        assert r.status_code == 400

    def test_register_short_password(self):
        r = requests.post(
            f"{GATEWAY}/auth/register",
            json={"username": "some_user", "password": "123", "role": "farmer"},
        )
        assert r.status_code == 422

    def test_register_short_username(self):
        r = requests.post(
            f"{GATEWAY}/auth/register",
            json={"username": "ab", "password": "password123", "role": "farmer"},
        )
        assert r.status_code == 422

    def test_register_invalid_role(self):
        r = requests.post(
            f"{GATEWAY}/auth/register",
            json={"username": "some_user2", "password": "password123", "role": "superuser"},
        )
        assert r.status_code == 422


class TestLogin:
    def test_login_success(self, farmer_token):
        assert isinstance(farmer_token, str)
        assert len(farmer_token) > 20

    def test_login_wrong_password(self):
        r = requests.post(
            f"{GATEWAY}/auth/login",
            json={"username": "admin", "password": "wrongpassword"},
        )
        assert r.status_code == 401

    def test_login_nonexistent_user(self):
        r = requests.post(
            f"{GATEWAY}/auth/login",
            json={"username": "ghost_user_xyz", "password": "password123"},
        )
        assert r.status_code == 401

    def test_login_returns_both_tokens(self, farmer_token):
        uid = str(uuid.uuid4())[:8]
        requests.post(
            f"{GATEWAY}/auth/register",
            json={"username": f"tok_{uid}", "password": "password123"},
        )
        r = requests.post(
            f"{GATEWAY}/auth/login",
            json={"username": f"tok_{uid}", "password": "password123"},
        )
        body = r.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body.get("token_type") == "bearer"


class TestMe:
    def test_me_with_valid_token(self, farmer_token):
        r = requests.get(f"{GATEWAY}/auth/me", headers=auth_header(farmer_token))
        assert r.status_code == 200
        body = r.json()
        assert "username" in body
        assert "role" in body
        assert body["role"] == "farmer"

    def test_me_without_token_returns_401(self):
        r = requests.get(f"{GATEWAY}/auth/me")
        assert r.status_code == 401

    def test_me_with_invalid_token_returns_401(self):
        r = requests.get(
            f"{GATEWAY}/auth/me",
            headers={"Authorization": "Bearer this.is.not.valid"},
        )
        assert r.status_code == 401

    def test_admin_me_returns_admin_role(self, admin_token):
        r = requests.get(f"{GATEWAY}/auth/me", headers=auth_header(admin_token))
        assert r.status_code == 200
        assert r.json()["role"] == "admin"
