"""
Tests for public endpoints — no authentication required.
"""
import requests
from conftest import GATEWAY


class TestHealth:
    def test_gateway_health(self):
        r = requests.get(f"{GATEWAY}/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["service"] == "gateway"

    def test_auth_health(self):
        r = requests.get(f"{GATEWAY}/health/auth")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"

    def test_vision_health_reachable(self):
        """Returns 200 if vision-ai is up, 502 if down — either way not 404/500."""
        r = requests.get(f"{GATEWAY}/health/vision", timeout=5)
        assert r.status_code in (200, 502, 503)

    def test_rag_health_reachable(self):
        r = requests.get(f"{GATEWAY}/health/rag", timeout=5)
        assert r.status_code in (200, 502, 503)


class TestPublicRoutes:
    def test_diseases_no_auth(self):
        """GET /diseases is public — should not require a token."""
        r = requests.get(f"{GATEWAY}/diseases", timeout=5)
        # 200 if vision-ai up, 502 if down — both acceptable (no 401/403)
        assert r.status_code not in (401, 403)

    def test_unknown_route_returns_404(self):
        r = requests.get(f"{GATEWAY}/this-does-not-exist")
        assert r.status_code == 404
        body = r.json()
        assert "error" in body

    def test_unknown_route_is_json(self):
        r = requests.get(f"{GATEWAY}/random/path/xyz")
        assert r.headers.get("Content-Type", "").startswith("application/json")


class TestCors:
    def test_options_preflight_returns_204(self):
        """Nginx should handle OPTIONS preflight without hitting any upstream."""
        r = requests.options(
            f"{GATEWAY}/predict",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            },
        )
        assert r.status_code == 204

    def test_cors_headers_present(self):
        r = requests.get(f"{GATEWAY}/health")
        assert "Access-Control-Allow-Origin" in r.headers
