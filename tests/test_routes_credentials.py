"""005-T040: credential vault routes per contracts/http-api.md. Thin routes
only — engine/credentials.py owns all vault logic. keyring is monkeypatched
to an in-memory fake so no test touches a real OS keychain."""
import pytest
from fastapi.testclient import TestClient


class FakeKeyringBackend:
    def __init__(self):
        self.store = {}

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def get_password(self, service, username):
        return self.store.get((service, username))

    def delete_password(self, service, username):
        self.store.pop((service, username), None)


@pytest.fixture()
def client(tmp_db, monkeypatch):
    monkeypatch.setenv("REFRESH_SYNC", "1")
    from engine import credentials, pipeline

    backend = FakeKeyringBackend()
    monkeypatch.setattr(credentials.keyring, "set_password", backend.set_password)
    monkeypatch.setattr(credentials.keyring, "get_password", backend.get_password)
    monkeypatch.setattr(credentials.keyring, "delete_password", backend.delete_password)
    monkeypatch.setattr(pipeline, "_source_names", lambda: [])
    monkeypatch.setattr(pipeline, "load_companies", lambda: [])
    from web.main import create_app

    return TestClient(create_app())


class TestSaveCredential:
    def test_save_returns_ok_and_never_echoes_password(self, client):
        resp = client.post(
            "/api/credentials",
            json={"domain": "jobs.example.com", "email": "me@example.com", "password": "hunter2"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"saved": True}
        assert "hunter2" not in resp.text


class TestListCredentials:
    def test_list_never_includes_password(self, client):
        client.post(
            "/api/credentials",
            json={"domain": "jobs.example.com", "email": "me@example.com", "password": "hunter2"},
        )
        resp = client.get("/api/credentials")
        assert resp.status_code == 200
        body = resp.json()
        assert body["domains"] == [{"domain": "jobs.example.com", "email": "me@example.com"}]
        assert body["default"] is None
        assert "hunter2" not in resp.text

    def test_list_empty_by_default(self, client):
        body = client.get("/api/credentials").json()
        assert body["domains"] == []
        assert body["default"] is None


class TestDefaultCredentialRoutes:
    """006-D: one default login used for any domain without its own
    override, so most sites need zero per-domain setup."""

    def test_save_default_returns_ok_never_echoes_password(self, client):
        resp = client.post(
            "/api/credentials/default",
            json={"email": "me@example.com", "password": "hunter2"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"saved": True}
        assert "hunter2" not in resp.text

    def test_list_credentials_reports_default_set_without_password(self, client):
        client.post(
            "/api/credentials/default",
            json={"email": "me@example.com", "password": "hunter2"},
        )
        resp = client.get("/api/credentials")
        body = resp.json()
        assert body["default"] == {"email": "me@example.com"}
        assert "hunter2" not in resp.text

    def test_list_credentials_default_null_when_unset(self, client):
        assert client.get("/api/credentials").json()["default"] is None

    def test_delete_default_route_does_not_collide_with_domain_route(self, client):
        """Regression: DELETE /api/credentials/default must hit the
        dedicated default-clearing route, not be swallowed by
        DELETE /api/credentials/{domain} with domain='default'."""
        client.post(
            "/api/credentials/default",
            json={"email": "me@example.com", "password": "hunter2"},
        )
        resp = client.delete("/api/credentials/default")
        assert resp.status_code == 200
        assert resp.json() == {"deleted": True}
        assert client.get("/api/credentials").json()["default"] is None


class TestDeleteCredential:
    def test_delete_removes_from_list(self, client):
        client.post(
            "/api/credentials",
            json={"domain": "jobs.example.com", "email": "me@example.com", "password": "hunter2"},
        )
        resp = client.delete("/api/credentials/jobs.example.com")
        assert resp.status_code == 200
        assert resp.json() == {"deleted": True}
        assert client.get("/api/credentials").json()["domains"] == []
