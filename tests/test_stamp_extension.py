"""010 T005: the app owns the unpacked extension folder — materialized
into the data dir and stamped with pairing.json at every launch. The
pairing file is the entire pairing UX (the extension re-reads it from disk
on every connect attempt)."""
import json

from engine import db
from scripts import stamp_extension


class TestStamp:
    def test_materializes_extension_and_pairing(self, tmp_db, tmp_path, monkeypatch):
        monkeypatch.setenv("JOBS_DATA_DIR", str(tmp_path / "data"))
        dest = stamp_extension.stamp(port=8123)
        assert (dest / "manifest.json").exists()
        assert (dest / "background" / "service-worker.js").exists()
        assert (dest / "content" / "scanner.js").exists()
        pairing = json.loads((dest / "pairing.json").read_text(encoding="utf-8"))
        assert pairing["port"] == 8123
        assert pairing["secret"] == db.get_bridge_secret()
        assert pairing["app_id"] == "jobengine"

    def test_restamp_updates_port_keeps_secret(self, tmp_db, tmp_path, monkeypatch):
        monkeypatch.setenv("JOBS_DATA_DIR", str(tmp_path / "data"))
        dest = stamp_extension.stamp(port=8123)
        secret_before = json.loads(
            (dest / "pairing.json").read_text(encoding="utf-8"))["secret"]
        dest2 = stamp_extension.stamp(port=9001)
        pairing = json.loads((dest2 / "pairing.json").read_text(encoding="utf-8"))
        assert dest2 == dest
        assert pairing["port"] == 9001
        assert pairing["secret"] == secret_before

    def test_source_tree_never_contains_pairing(self):
        """pairing.json must exist only in the stamped data-dir copy —
        committing one to the repo source would ship a machine's secret."""
        assert not (stamp_extension.source_dir() / "pairing.json").exists()


class TestStampHardened:
    """015 (T008, FR-007/FR-008/FR-015): stamping is verified, observable,
    and survives copy trouble — the silent-death class that shipped in 1.4.0
    (stamp crashed, nothing noticed, pairing dead) becomes impossible."""

    def _status(self, tmp_path):
        import json as json_mod

        path = tmp_path / "data" / "stamp_status.json"
        assert path.exists(), "stamp must record its outcome every run"
        return json_mod.loads(path.read_text(encoding="utf-8"))

    def test_success_writes_verified_status_and_manifest_version(
            self, tmp_db, tmp_path, monkeypatch):
        from engine import APP_VERSION

        monkeypatch.setenv("JOBS_DATA_DIR", str(tmp_path / "data"))
        dest = stamp_extension.stamp(port=8123)

        status = self._status(tmp_path)
        assert status["ok"] is True
        assert status["error"] is None
        assert status["port"] == 8123
        assert status["app_version"] == APP_VERSION
        assert status["at"]
        # R13: the STAGED manifest tracks the app release that stamped it
        manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["version"] == APP_VERSION

    def test_verify_failure_recorded_and_raised(self, tmp_db, tmp_path, monkeypatch):
        import pytest

        monkeypatch.setenv("JOBS_DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setattr(
            stamp_extension, "_verify_pairing",
            lambda dest, port, secret: (_ for _ in ()).throw(
                ValueError("read-back mismatch")),
        )
        with pytest.raises(ValueError):
            stamp_extension.stamp(port=8123)
        status = self._status(tmp_path)
        assert status["ok"] is False
        assert "read-back mismatch" in status["error"]

    def test_pairing_written_even_when_copy_fails_over_existing_files(
            self, tmp_db, tmp_path, monkeypatch):
        """A locked/failed copy with a previously-stamped folder must NOT
        leave a stale port behind — pairing.json still updates (the old
        files keep working; a stale port kills the connection entirely)."""
        import shutil as shutil_mod

        monkeypatch.setenv("JOBS_DATA_DIR", str(tmp_path / "data"))
        dest = stamp_extension.stamp(port=8123)  # populate once, for real

        def broken_copy(*args, **kwargs):
            raise OSError("files locked by the browser")

        monkeypatch.setattr(shutil_mod, "copytree", broken_copy)
        dest2 = stamp_extension.stamp(port=9001)
        assert dest2 == dest
        pairing = json.loads((dest / "pairing.json").read_text(encoding="utf-8"))
        assert pairing["port"] == 9001  # fresh port despite the failed copy
        status = self._status(tmp_path)
        assert status["ok"] is True
        assert "locked" in (status["copy_warning"] or "")

    def test_stamp_module_import_allowlist(self):
        """FR-009: the stamp path may import NOTHING heavy — pydantic's
        import chain breaking in the frozen app is exactly what silently
        killed pairing. AST-enforced, not convention."""
        import ast
        import pathlib

        src = pathlib.Path("scripts/stamp_extension.py").read_text(encoding="utf-8")
        modules = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.add(node.module or "")
        allowed = {"__future__", "argparse", "json", "shutil", "sys",
                   "pathlib", "datetime", "engine", "engine.db",
                   "engine.paths", "engine.autofill.bridge_const"}
        assert modules <= allowed, f"forbidden imports in stamp path: {modules - allowed}"
        assert "engine.autofill.ext_protocol" not in modules


class TestBridgeConst:
    """015 (T002/FR-009): protocol constants live in a dependency-free module
    so the stamp path can read them without importing pydantic — the exact
    import chain that silently killed pairing in the shipped 1.4.0 app."""

    def test_values_and_single_source(self):
        from engine.autofill import bridge_const, ext_protocol

        assert bridge_const.PROTOCOL_V == 1
        assert bridge_const.APP_ID == "jobengine"
        # ext_protocol re-exports FROM bridge_const — one source, no drift
        assert ext_protocol.PROTOCOL_V == bridge_const.PROTOCOL_V

    def test_bridge_const_imports_nothing_heavy(self):
        import ast
        import pathlib

        src = pathlib.Path("engine/autofill/bridge_const.py").read_text(
            encoding="utf-8")
        tree = ast.parse(src)
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.add(node.module or "")
        assert modules <= {"__future__"}, f"unexpected imports: {modules}"
