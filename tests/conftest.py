import pytest


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Point the engine at a fresh temp database for each test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("JOBS_DB_PATH", str(db_path))
    from engine import db

    db.init_db()
    return db_path
