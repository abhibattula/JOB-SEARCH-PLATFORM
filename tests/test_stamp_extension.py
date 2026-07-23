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
