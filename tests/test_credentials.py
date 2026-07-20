"""005-T037: engine/credentials.py — OS-keychain-backed credential vault.

keyring itself is monkeypatched to an in-memory fake in every test — this
avoids depending on a real OS credential store being available in CI/dev,
and keeps these tests fast, deterministic, and side-effect-free (no test
should ever touch the developer's actual keychain).
"""
import pytest

from engine import credentials


class FakeKeyringBackend:
    """In-memory stand-in for the OS keychain."""

    def __init__(self):
        self.store: dict[tuple[str, str], str] = {}

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def get_password(self, service, username):
        return self.store.get((service, username))

    def delete_password(self, service, username):
        self.store.pop((service, username), None)


@pytest.fixture()
def fake_keyring(monkeypatch):
    backend = FakeKeyringBackend()
    monkeypatch.setattr(credentials.keyring, "set_password", backend.set_password)
    monkeypatch.setattr(credentials.keyring, "get_password", backend.get_password)
    monkeypatch.setattr(credentials.keyring, "delete_password", backend.delete_password)
    return backend


class TestSaveAndGet:
    def test_save_then_get_roundtrip(self, tmp_db, fake_keyring):
        credentials.save("jobs.example.com", "me@example.com", "hunter2")
        result = credentials.get("jobs.example.com")
        assert result == {"email": "me@example.com", "password": "hunter2"}

    def test_get_missing_domain_returns_none(self, tmp_db, fake_keyring):
        assert credentials.get("never-saved.example.com") is None

    def test_password_never_touches_sqlite(self, tmp_db, fake_keyring):
        """FR-017/data-model.md invariant: the secret lives only in the
        (fake) keychain — the settings table only ever holds the email hint."""
        from engine import db

        credentials.save("jobs.example.com", "me@example.com", "hunter2")
        with db._conn() as conn:
            rows = conn.execute("SELECT value FROM settings").fetchall()
        values = [r["value"] for r in rows]
        assert not any("hunter2" in v for v in values)

    def test_save_overwrites_existing_credential(self, tmp_db, fake_keyring):
        credentials.save("jobs.example.com", "me@example.com", "old-pw")
        credentials.save("jobs.example.com", "me@example.com", "new-pw")
        assert credentials.get("jobs.example.com")["password"] == "new-pw"


class TestDelete:
    def test_delete_clears_both_keychain_and_settings_row(self, tmp_db, fake_keyring):
        credentials.save("jobs.example.com", "me@example.com", "hunter2")
        credentials.delete("jobs.example.com")

        assert credentials.get("jobs.example.com") is None
        assert ("jobs.example.com", "me@example.com") not in fake_keyring.store
        assert "jobs.example.com" not in {d["domain"] for d in credentials.list_domains()}

    def test_delete_nonexistent_domain_is_a_noop(self, tmp_db, fake_keyring):
        credentials.delete("never-saved.example.com")  # must not raise


class TestListDomains:
    def test_list_domains_never_includes_password(self, tmp_db, fake_keyring):
        credentials.save("a.example.com", "a@example.com", "secret-a")
        credentials.save("b.example.com", "b@example.com", "secret-b")

        domains = credentials.list_domains()

        assert {"domain": "a.example.com", "email": "a@example.com"} in domains
        assert {"domain": "b.example.com", "email": "b@example.com"} in domains
        for d in domains:
            assert "password" not in d
            assert all("secret" not in str(v) for v in d.values())

    def test_list_domains_empty_by_default(self, tmp_db, fake_keyring):
        assert credentials.list_domains() == []
