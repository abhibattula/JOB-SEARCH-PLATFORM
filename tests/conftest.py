import pytest


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Every test gets its own database path AND data dir — no test may
    touch data/jobs.db or write files (stored resumes, tailored PDFs,
    007) into the real data directory."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("JOBS_DB_PATH", str(db_path))
    monkeypatch.setenv("JOBS_DATA_DIR", str(tmp_path))
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


@pytest.fixture(autouse=True)
def _isolated_profile_import_state(monkeypatch):
    """009: engine.profile_import keeps its state machine in module-level
    globals (session-scoped by design). Reset around every test, and join
    any background import thread BEFORE monkeypatch teardown (depending on
    `monkeypatch` orders this teardown first) — a leaked thread that
    outlives its stubs sees the real bundled model and races the next
    test's fresh database."""
    from engine import profile_import

    profile_import.reset_state()
    from engine.autofill import ext_backend

    ext_backend.reset_for_tests()
    yield
    profile_import.join_for_tests()
    profile_import.reset_state()
    ext_backend.reset_for_tests()
