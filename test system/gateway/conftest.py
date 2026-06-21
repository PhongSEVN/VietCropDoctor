"""
Shared fixtures for gateway system tests.

Requires the gateway + auth + postgres + redis stack to be running:
    docker compose up -d postgres redis auth gateway
"""
import uuid
import pytest
import requests

GATEWAY = "http://localhost:8000"


def _register_and_login(username: str, password: str, role: str = "farmer") -> str:
    """Register a user (ignore if already exists) and return a JWT access token."""
    requests.post(
        f"{GATEWAY}/auth/register",
        json={"username": username, "password": password, "role": role},
    )
    resp = requests.post(
        f"{GATEWAY}/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, f"Login failed for {username}: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="session")
def base_url() -> str:
    return GATEWAY


@pytest.fixture(scope="session")
def farmer_token() -> str:
    uid = str(uuid.uuid4())[:8]
    return _register_and_login(f"test_farmer_{uid}", "testpass123", "farmer")


@pytest.fixture(scope="session")
def admin_token() -> str:
    """Uses the seeded admin account from infra/postgres/init.sql."""
    resp = requests.post(
        f"{GATEWAY}/auth/login",
        json={"username": "admin", "password": "Admin@1234"},
    )
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json()["access_token"]


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
