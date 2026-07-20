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


@pytest.fixture(autouse=True)
def _isolated_browser_controller_state():
    """005: engine.autofill.browser_controller keeps its queue state in
    module-level globals (by design — it's a singleton automation session,
    not per-request). Each test's SQLite db is isolated (_isolated_db above),
    but that in-memory state is not, so a queue left "running" by one test
    would leak into the next and reference a job_id from a database that no
    longer exists. Reset before and after every test."""
    from engine.autofill import browser_controller

    browser_controller.stop_queue()
    yield
    browser_controller.stop_queue()
