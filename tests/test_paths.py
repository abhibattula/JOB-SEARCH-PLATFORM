"""003-WS3: data/resource path resolution for dev vs frozen (installed) runs."""
import sys
from pathlib import Path

from engine import db, paths


class TestDataDir:
    def test_dev_mode_uses_repo_data(self, monkeypatch):
        monkeypatch.delenv("JOBS_DATA_DIR", raising=False)
        monkeypatch.delattr(sys, "frozen", raising=False)
        assert paths.data_dir() == Path("data")

    def test_env_override_wins(self, monkeypatch, tmp_path):
        monkeypatch.setenv("JOBS_DATA_DIR", str(tmp_path / "custom"))
        assert paths.data_dir() == tmp_path / "custom"

    def test_frozen_uses_platform_dir(self, monkeypatch, tmp_path):
        monkeypatch.delenv("JOBS_DATA_DIR", raising=False)
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))      # windows base
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))     # linux base
        result = paths.data_dir()
        assert result.name == "JobEngine"
        # windows/linux resolve under tmp_path; macOS under ~/Library
        assert str(tmp_path) in str(result) or "Application Support" in str(result)


class TestResourcePath:
    def test_dev_mode_is_repo_relative(self, monkeypatch):
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        assert paths.resource_path("companies.yml").exists()

    def test_meipass_wins_when_frozen(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
        assert paths.resource_path("web/templates") == tmp_path / "web/templates"


class TestDbPathIntegration:
    def test_env_jobs_db_path_still_wins(self, monkeypatch, tmp_path):
        monkeypatch.setenv("JOBS_DB_PATH", str(tmp_path / "x.db"))
        assert db.get_db_path() == tmp_path / "x.db"

    def test_falls_back_to_data_dir(self, monkeypatch, tmp_path):
        monkeypatch.delenv("JOBS_DB_PATH", raising=False)
        monkeypatch.setenv("JOBS_DATA_DIR", str(tmp_path))
        assert db.get_db_path() == tmp_path / "jobs.db"


class TestBundledSponsorshipBootstrap:
    def test_loads_bundled_csv_when_table_empty(self, tmp_db, monkeypatch, tmp_path):
        bundle = tmp_path / "assets" / "uscis"
        bundle.mkdir(parents=True)
        (bundle / "h1b_sample.csv").write_text(
            "Fiscal Year,Employer (Petitioner) Name,Initial Approval,Continuing Approval\n"
            "2023,NVIDIA CORPORATION,900,600\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            paths, "resource_path",
            lambda rel: bundle if rel == "assets/uscis" else Path(rel),
        )
        from web.main import _bootstrap_sponsorship

        _bootstrap_sponsorship()
        assert db.h1b_employer_count() == 1
        # second call is a cheap no-op
        _bootstrap_sponsorship()
        assert db.h1b_employer_count() == 1
