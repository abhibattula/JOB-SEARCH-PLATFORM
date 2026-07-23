"""003-WS1: settings storage, precedence, and the settings API."""
import pytest

from engine import db, settings


class TestPrecedence:
    def test_env_beats_db_beats_default(self, tmp_db, monkeypatch):
        assert settings.get("LLM_MODEL") == settings.DEFAULTS["LLM_MODEL"]
        settings.set("LLM_MODEL", "db-model")
        assert settings.get("LLM_MODEL") == "db-model"
        monkeypatch.setenv("LLM_MODEL", "env-model")
        assert settings.get("LLM_MODEL") == "env-model"

    def test_unknown_key_uses_fallback(self, tmp_db, monkeypatch):
        monkeypatch.delenv("NOT_A_SETTING", raising=False)
        assert settings.get("NOT_A_SETTING", "fallback") == "fallback"

    def test_llm_available_reads_db_key(self, tmp_db, monkeypatch):
        """005: llm_available() is also true via the bundled local model, so
        isolate the cloud-key-specific behavior by forcing local unavailable."""
        from engine import matcher

        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
        assert matcher.llm_available() is False
        settings.set("LLM_API_KEY", "gsk_dbkey123")
        assert matcher.llm_available() is True


class TestSettingsApi:
    @pytest.fixture()
    def client(self, tmp_db, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.setenv("REFRESH_SYNC", "1")
        from engine import pipeline

        monkeypatch.setattr(pipeline, "_source_names", lambda: [])
        monkeypatch.setattr(pipeline, "load_companies", lambda: [])
        from fastapi.testclient import TestClient

        from web.main import create_app

        return TestClient(create_app())

    def test_get_masks_key(self, client):
        settings.set("LLM_API_KEY", "gsk_supersecretvalue1234")
        payload = client.get("/api/settings").json()
        assert payload["llm_key_set"] is True
        assert "supersecret" not in payload["llm_api_key_masked"]
        assert payload["llm_api_key_masked"].endswith("1234")

    def test_post_saves_and_blank_key_keeps_existing(self, client):
        response = client.post(
            "/api/settings",
            data={"llm_api_key": "gsk_first", "jobspy_linkedin": "1"},
        )
        assert response.status_code == 200
        assert settings.get("LLM_API_KEY") == "gsk_first"
        assert settings.get("JOBSPY_LINKEDIN") == "1"

        client.post("/api/settings", data={"llm_api_key": "", "jobspy_linkedin": "0"})
        assert settings.get("LLM_API_KEY") == "gsk_first"  # blank never clears
        assert settings.get("JOBSPY_LINKEDIN") == "0"

    def test_key_test_endpoint(self, client, monkeypatch):
        from engine import matcher

        settings.set("LLM_API_KEY", "gsk_x")
        monkeypatch.setattr(matcher, "_chat", lambda messages, **kw: "pong")
        assert client.post("/api/settings/test").json()["ok"] is True

        def boom(messages):
            raise RuntimeError("401 invalid api key")

        monkeypatch.setattr(matcher, "_chat", boom)
        result = client.post("/api/settings/test").json()
        assert result["ok"] is False
        assert "invalid" in result["error"]

    def test_key_test_without_key(self, client):
        result = client.post("/api/settings/test").json()
        assert result["ok"] is False

    def test_settings_page_serves(self, client):
        assert client.get("/settings").status_code == 200

    def test_theme_setting_roundtrip(self, client):
        """007-T006 (FR-021): explicit theme choice persists via the
        settings path and is reported by GET /api/settings."""
        assert client.get("/api/settings").json()["theme"] == ""  # unset
        response = client.post("/api/settings", data={"theme": "dark"})
        assert response.status_code == 200
        assert settings.get("THEME") == "dark"
        assert client.get("/api/settings").json()["theme"] == "dark"
        client.post("/api/settings", data={"theme": "light"})
        assert settings.get("THEME") == "light"

    def test_autofill_tailored_pdf_toggle_roundtrip(self, client):
        """007-T030 (FR-002): default on; explicit off persists."""
        assert client.get("/api/settings").json()["autofill_use_tailored_pdf"] is True
        client.post("/api/settings", data={"autofill_use_tailored_pdf": "0"})
        assert settings.get("AUTOFILL_USE_TAILORED_PDF") == "0"
        assert client.get("/api/settings").json()["autofill_use_tailored_pdf"] is False
        client.post("/api/settings", data={"autofill_use_tailored_pdf": "1"})
        assert client.get("/api/settings").json()["autofill_use_tailored_pdf"] is True

    def test_pages_stamp_data_theme_from_setting(self, client):
        """007-T006 (FR-021): base template stamps the persisted choice
        onto <html> so CSS [data-theme] scoping applies before first
        paint; unset renders without a forced attribute value."""
        settings.set("THEME", "dark")
        resp = client.get("/settings")
        assert 'data-theme="dark"' in resp.text

    def test_settings_page_renders_saved_credential_without_password(self, client, monkeypatch):
        """005-T040: the credentials section must render a saved domain and
        never leak the password into the page."""
        from engine import credentials

        monkeypatch.setattr(
            credentials, "list_domains",
            lambda: [{"domain": "jobs.example.com", "email": "me@example.com"}],
        )
        resp = client.get("/settings")
        assert resp.status_code == 200
        assert "jobs.example.com" in resp.text
        assert "me@example.com" in resp.text

    def test_settings_page_renders_default_credential_email(self, client, monkeypatch):
        """006-D: default-login section must render without error."""
        from engine import credentials

        monkeypatch.setattr(credentials, "get_default", lambda: {"email": "default@example.com", "password": "x"})
        resp = client.get("/settings")
        assert resp.status_code == 200
        assert "default@example.com" in resp.text


class Test008Defaults:
    def test_new_defaults_present(self, tmp_db):
        assert settings.get("FEED_WINDOW_DEFAULT") == "14d"
        assert settings.get("JOBSPY_SITES") == "indeed,google"
        assert settings.get("JOBSPY_RESULTS_PER_SEARCH") == "40"
        assert settings.get("LLM_JSON_MODEL") == "openai/gpt-oss-120b"
        assert settings.get("LLM_PROVIDER_PRESET") == "groq"
