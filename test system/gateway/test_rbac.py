"""
Tests for role-based access control enforced by Nginx auth_request.

Matrix:
  Route              | No token | farmer | agronomist | admin
  /predict           |   401    |  pass* |   pass*    | pass*
  /query             |   401    |  pass* |   pass*    | pass*
  /analytics/summary |   401    |  403   |   pass*    | pass*
  /ingest            |   401    |  403   |    403     | pass*
  /collection DELETE |   401    |  403   |    403     | pass*

  *pass = not 401/403 (upstream may return 502 if service is down)
"""
import uuid
import requests
from conftest import GATEWAY, _register_and_login, auth_header


def _agronomist_token() -> str:
    uid = str(uuid.uuid4())[:8]
    return _register_and_login(f"agro_{uid}", "testpass123", "agronomist")


class TestPredictRBAC:
    def test_predict_no_token_returns_401(self):
        r = requests.post(f"{GATEWAY}/predict", data={}, timeout=5)
        assert r.status_code == 401

    def test_predict_invalid_token_returns_401(self):
        r = requests.post(
            f"{GATEWAY}/predict",
            headers={"Authorization": "Bearer fake.token.here"},
            timeout=5,
        )
        assert r.status_code == 401

    def test_predict_farmer_passes_auth(self, farmer_token):
        """Farmer is allowed — gateway forwards to vision-ai (may 502 if service down)."""
        r = requests.post(
            f"{GATEWAY}/predict",
            headers=auth_header(farmer_token),
            timeout=5,
        )
        assert r.status_code not in (401, 403)

    def test_predict_admin_passes_auth(self, admin_token):
        r = requests.post(
            f"{GATEWAY}/predict",
            headers=auth_header(admin_token),
            timeout=5,
        )
        assert r.status_code not in (401, 403)


class TestQueryRBAC:
    def test_query_no_token_returns_401(self):
        r = requests.post(
            f"{GATEWAY}/query",
            json={"question": "test", "session_id": "x"},
            timeout=5,
        )
        assert r.status_code == 401

    def test_query_farmer_passes_auth(self, farmer_token):
        r = requests.post(
            f"{GATEWAY}/query",
            headers=auth_header(farmer_token),
            json={"question": "bệnh đạo ôn", "session_id": "test-sess"},
            timeout=10,
        )
        assert r.status_code not in (401, 403)


class TestAnalyticsRBAC:
    def test_analytics_no_token_returns_401(self):
        r = requests.get(f"{GATEWAY}/analytics/summary", timeout=5)
        assert r.status_code == 401

    def test_analytics_farmer_returns_403(self, farmer_token):
        """Farmers cannot access analytics — requires agronomist or admin."""
        r = requests.get(
            f"{GATEWAY}/analytics/summary",
            headers=auth_header(farmer_token),
            timeout=5,
        )
        assert r.status_code == 403

    def test_analytics_agronomist_passes_auth(self):
        token = _agronomist_token()
        r = requests.get(
            f"{GATEWAY}/analytics/summary",
            headers=auth_header(token),
            timeout=5,
        )
        assert r.status_code not in (401, 403)

    def test_analytics_admin_passes_auth(self, admin_token):
        r = requests.get(
            f"{GATEWAY}/analytics/summary",
            headers=auth_header(admin_token),
            timeout=5,
        )
        assert r.status_code not in (401, 403)


class TestIngestRBAC:
    def test_ingest_no_token_returns_401(self):
        r = requests.post(f"{GATEWAY}/ingest", json={}, timeout=5)
        assert r.status_code == 401

    def test_ingest_farmer_returns_403(self, farmer_token):
        r = requests.post(
            f"{GATEWAY}/ingest",
            headers=auth_header(farmer_token),
            json={},
            timeout=5,
        )
        assert r.status_code == 403

    def test_ingest_agronomist_returns_403(self):
        token = _agronomist_token()
        r = requests.post(
            f"{GATEWAY}/ingest",
            headers=auth_header(token),
            json={},
            timeout=5,
        )
        assert r.status_code == 403

    def test_ingest_admin_passes_auth(self, admin_token):
        """Admin is allowed — gateway forwards to rag-engine (may 502 if service down)."""
        r = requests.post(
            f"{GATEWAY}/ingest",
            headers=auth_header(admin_token),
            json={},
            timeout=5,
        )
        assert r.status_code not in (401, 403)

    def test_collection_delete_farmer_returns_403(self, farmer_token):
        r = requests.delete(
            f"{GATEWAY}/collection",
            headers=auth_header(farmer_token),
            timeout=5,
        )
        assert r.status_code == 403

    def test_collection_delete_admin_passes_auth(self, admin_token):
        r = requests.delete(
            f"{GATEWAY}/collection",
            headers=auth_header(admin_token),
            timeout=5,
        )
        assert r.status_code not in (401, 403)


class TestAuthErrorFormat:
    def test_401_response_is_json(self):
        r = requests.get(f"{GATEWAY}/analytics/summary")
        assert r.headers.get("Content-Type", "").startswith("application/json")
        body = r.json()
        assert "error" in body

    def test_403_response_is_json(self, farmer_token):
        r = requests.get(
            f"{GATEWAY}/analytics/summary",
            headers=auth_header(farmer_token),
        )
        assert r.headers.get("Content-Type", "").startswith("application/json")
        body = r.json()
        assert "error" in body
