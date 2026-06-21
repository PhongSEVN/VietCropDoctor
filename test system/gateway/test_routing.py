"""
Tests that verify Nginx routes each URL prefix to the correct upstream service.
Checks response shape/headers that are characteristic of each service.
"""
import requests
from conftest import GATEWAY, auth_header


class TestAuthRouting:
    def test_auth_register_routed_to_auth_service(self):
        """If routed to auth service, invalid body returns 422 (FastAPI validation)."""
        r = requests.post(f"{GATEWAY}/auth/register", json={"bad": "data"})
        assert r.status_code == 422

    def test_auth_login_routed_to_auth_service(self):
        r = requests.post(f"{GATEWAY}/auth/login", json={"username": "x", "password": "y"})
        # 401 means auth service is responding (not 404/502)
        assert r.status_code == 401

    def test_auth_service_health_distinct_from_gateway(self):
        gateway = requests.get(f"{GATEWAY}/health").json()
        auth = requests.get(f"{GATEWAY}/health/auth").json()
        # Gateway says "gateway", auth says "auth"
        assert gateway.get("service") == "gateway"
        assert auth.get("service") == "auth"


class TestVisionAIRouting:
    def test_predict_requires_multipart_form(self, farmer_token):
        """vision-ai /predict expects multipart — sending JSON body → 422 from vision-ai."""
        r = requests.post(
            f"{GATEWAY}/predict",
            headers=auth_header(farmer_token),
            json={"wrong": "format"},
            timeout=5,
        )
        # 422 = reached vision-ai and it validated the request
        # 502 = vision-ai not running but auth passed
        assert r.status_code in (422, 502, 503)

    def test_diseases_routed_to_vision_ai(self):
        r = requests.get(f"{GATEWAY}/diseases", timeout=5)
        # 200 with diseases list OR 502 if vision-ai down
        assert r.status_code in (200, 502, 503)
        if r.status_code == 200:
            assert "diseases" in r.json()


class TestRAGRouting:
    def test_query_body_validation_from_rag_engine(self, farmer_token):
        """Sending empty body to /query → 422 from rag-engine (FastAPI validation)."""
        r = requests.post(
            f"{GATEWAY}/query",
            headers=auth_header(farmer_token),
            json={},
            timeout=10,
        )
        assert r.status_code in (422, 502, 503)

    def test_chat_is_public(self):
        """POST /chat should not require auth."""
        r = requests.post(
            f"{GATEWAY}/chat",
            json={"question": "hello", "session_id": "test"},
            timeout=10,
        )
        assert r.status_code not in (401, 403)


class TestSecurityHeaders:
    def test_x_content_type_options(self):
        r = requests.get(f"{GATEWAY}/health")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_frame_options(self):
        r = requests.get(f"{GATEWAY}/health")
        assert r.headers.get("X-Frame-Options") == "DENY"

    def test_xss_protection(self):
        r = requests.get(f"{GATEWAY}/health")
        assert "X-XSS-Protection" in r.headers

    def test_referrer_policy(self):
        r = requests.get(f"{GATEWAY}/health")
        assert "Referrer-Policy" in r.headers
