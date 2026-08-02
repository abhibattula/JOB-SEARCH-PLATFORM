"""020 (US2/US3): the background AI assessment pass.

engine/upgrade.py promotes quick-scored ("basic") jobs to full AI assessment,
one at a time, best-first by semantic similarity, yielding entirely to an
active application fill session. It is the half of scoring that costs ~67 s a
job on the applicant's laptop, so it lives OUTSIDE the refresh run — the
inline version held that run open for 2 h 47 m and got superseded before it
could finish (research R2).

No real model is ever loaded here; every test stubs the assessor.
"""
from __future__ import annotations

import threading

import pytest

from engine import upgrade


@pytest.fixture(autouse=True)
def _fresh_upgrade():
    upgrade.reset_for_tests()
    yield
    upgrade.reset_for_tests()


class TestProgressShape020:
    """T003 (FR-011): the read-only projection the status endpoint renders.

    It has to answer safely before anything has ever run — the feed asks on
    every page load, including the very first one after install.
    """

    _KEYS = {"running", "done", "total", "failed", "paused_for_session"}

    def test_defaults_before_any_pass(self):
        snap = upgrade.progress()
        assert set(snap) == self._KEYS
        assert snap == {"running": False, "done": 0, "total": 0,
                        "failed": 0, "paused_for_session": False}

    def test_shape_is_always_complete(self):
        """Never a partial dict — the template reads every key unconditionally,
        so a missing one is a 500 on the feed rather than a blank badge."""
        for key, kind in (("running", bool), ("done", int), ("total", int),
                          ("failed", int), ("paused_for_session", bool)):
            assert isinstance(upgrade.progress()[key], kind), key

    def test_snapshot_is_a_copy(self):
        """A caller mutating what it got back must not corrupt pass state."""
        snap = upgrade.progress()
        snap["done"] = 999
        assert upgrade.progress()["done"] == 0

    def test_safe_from_any_thread_and_does_not_block(self):
        """The status endpoint calls this while a pass may be mid-assessment;
        it must never wait on the pass (contracts/upgrade-api.md)."""
        seen: list[dict] = []
        errors: list[BaseException] = []

        def read():
            try:
                for _ in range(50):
                    seen.append(upgrade.progress())
            except BaseException as exc:  # noqa: BLE001 — surface it
                errors.append(exc)

        threads = [threading.Thread(target=read) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
            assert not t.is_alive(), "progress() blocked a reader"
        assert not errors
        assert len(seen) == 200
        assert all(set(s) == self._KEYS for s in seen)

    def test_reset_restores_defaults(self):
        upgrade.reset_for_tests()
        assert upgrade.progress() == {"running": False, "done": 0, "total": 0,
                                      "failed": 0, "paused_for_session": False}


def _imported_modules(module) -> set[str]:
    """Every module name this module imports, including inside functions.

    Parsed from the AST, not grepped from the source: a substring search
    matches the module's own docstring prose ("imports nothing from web/") and
    would pass or fail for reasons that have nothing to do with the imports.
    """
    import ast
    import inspect

    names: set[str] = set()
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
            # `from . import db` — the module IS the alias, and node.module is
            # None. This codebase imports that way almost everywhere, so
            # reading node.module alone would see nothing at all.
            names.update(alias.name for alias in node.names)
    return names


class TestModuleBoundaries020:
    """Principle IV + guarantee L5. Cheap to assert, and the exact mistake
    that would make this module unusable from the CLI."""

    def test_does_not_import_web(self):
        imported = _imported_modules(upgrade)
        assert not any(name == "web" or name.startswith("web.")
                       for name in imported), imported

    def test_does_not_import_pipeline(self):
        """pipeline imports upgrade; the dependency runs ONE way only. A cycle
        here would break `from engine import pipeline` at import time."""
        imported = _imported_modules(upgrade)
        assert not any(name.split(".")[-1] == "pipeline"
                       for name in imported), imported

    def test_the_boundary_check_can_actually_fail(self):
        """The 019 lesson: never let an assertion pass for a reason unrelated
        to what it claims. Plant both forbidden imports — in the two shapes
        this codebase actually writes — and prove the detector sees them.

        This caught a real bug when it was written: the first detector read
        only `node.module`, so `from . import pipeline` (module=None, the
        dominant style in engine/) was invisible to it.
        """
        import textwrap
        import types

        offender = types.ModuleType("offender")
        offender.__source__ = textwrap.dedent('''
            """A module whose docstring mentions web/ and pipeline harmlessly."""
            from web import main
            def f():
                from . import pipeline
        ''')

        import ast
        import inspect

        real_getsource = inspect.getsource
        try:
            inspect.getsource = lambda m: m.__source__
            found = _imported_modules(offender)
        finally:
            inspect.getsource = real_getsource

        assert "web" in found, found
        assert "pipeline" in found, found
        assert ast is not None  # import used above
