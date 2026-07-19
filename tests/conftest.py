import pytest


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Every test gets its own database path — no test may touch data/jobs.db."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("JOBS_DB_PATH", str(db_path))
    return db_path


@pytest.fixture()
def tmp_db(_isolated_db):
    """Initialized temp database for tests that exercise the schema directly."""
    from engine import db

    db.init_db()
    return _isolated_db
