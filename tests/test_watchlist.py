"""008 T005/T028: DB-backed company watchlist — seeding, CRUD, runtime load."""
import pytest

from engine import db, watchlist


@pytest.fixture()
def seed_yaml(tmp_path, monkeypatch):
    path = tmp_path / "companies.yml"
    path.write_text(
        "companies:\n"
        "  - {name: Stripe, ats: greenhouse, slug: stripe}\n"
        "  - {name: Tenstorrent, ats: lever, slug: tenstorrent}\n"
        "  - {name: Acme WD, ats: workday, host: acme.wd1.myworkdayjobs.com,"
        " site: External, search: engineer}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("COMPANIES_PATH", str(path))
    return path


class TestSeeding:
    def test_seeds_from_yaml_once(self, tmp_db, seed_yaml):
        inserted = watchlist.ensure_seeded()
        assert inserted == 3
        rows = watchlist.list_all()
        assert len(rows) == 3
        assert all(r["origin"] == "shipped" and r["enabled"] for r in rows)

    def test_reseed_inserts_only_unknown_and_respects_user_state(
        self, tmp_db, seed_yaml
    ):
        watchlist.ensure_seeded()
        rows = watchlist.list_all()
        stripe = next(r for r in rows if r["slug"] == "stripe")
        watchlist.set_enabled(stripe["id"], False)
        user_row = watchlist.add("ashby", "sifive", name="SiFive")
        assert watchlist.ensure_seeded() == 0  # nothing new
        rows = {r["slug"]: r for r in watchlist.list_all()}
        assert rows["stripe"]["enabled"] is False  # user toggle survives
        assert rows["sifive"]["origin"] == "user"
        assert user_row["id"] == rows["sifive"]["id"]

    def test_workday_extra_fields_round_trip(self, tmp_db, seed_yaml):
        watchlist.ensure_seeded()
        active = watchlist.load_active()
        wd = next(e for e in active if e["ats"] == "workday")
        assert wd["host"] == "acme.wd1.myworkdayjobs.com"
        assert wd["site"] == "External"
        assert wd["search"] == "engineer"


class TestCrud:
    def test_add_validates_and_rejects_duplicates(self, tmp_db, seed_yaml):
        watchlist.ensure_seeded()
        with pytest.raises(ValueError):
            watchlist.add("notanats", "x")
        with pytest.raises(ValueError):
            watchlist.add("greenhouse", "stripe")  # duplicate

    def test_remove_semantics_user_deleted_shipped_disabled(
        self, tmp_db, seed_yaml
    ):
        watchlist.ensure_seeded()
        user_row = watchlist.add("greenhouse", "figma2", name="Figma2")
        assert watchlist.remove(user_row["id"]) == "deleted"
        rows = {r["slug"]: r for r in watchlist.list_all()}
        assert "figma2" not in rows
        stripe = rows["stripe"]
        assert watchlist.remove(stripe["id"]) == "disabled"
        rows = {r["slug"]: r for r in watchlist.list_all()}
        assert rows["stripe"]["enabled"] is False

    def test_load_active_excludes_disabled(self, tmp_db, seed_yaml):
        watchlist.ensure_seeded()
        rows = watchlist.list_all()
        stripe = next(r for r in rows if r["slug"] == "stripe")
        watchlist.set_enabled(stripe["id"], False)
        active_slugs = {e["slug"] for e in watchlist.load_active()}
        assert "stripe" not in active_slugs
        assert "tenstorrent" in active_slugs

    def test_mark_ok_stamps_last_ok_at(self, tmp_db, seed_yaml):
        watchlist.ensure_seeded()
        watchlist.mark_ok("greenhouse", "stripe")
        rows = {r["slug"]: r for r in watchlist.list_all()}
        assert rows["stripe"]["last_ok_at"]
        assert rows["tenstorrent"]["last_ok_at"] is None


class TestRuntimeLoad:
    """T028: after seeding, the DB is the single runtime source of boards —
    user toggles change what the pipeline fetches without touching YAML."""

    def test_pipeline_load_companies_reads_watchlist(self, tmp_db, seed_yaml):
        from engine import pipeline

        entries = pipeline.load_companies()  # auto-seeds, then serves from DB
        slugs = {e["slug"] for e in entries if e["ats"] != "workday"}
        assert "stripe" in slugs and "tenstorrent" in slugs
        stripe = next(r for r in watchlist.list_all() if r["slug"] == "stripe")
        watchlist.set_enabled(stripe["id"], False)
        slugs = {e.get("slug") for e in pipeline.load_companies()}
        assert "stripe" not in slugs

    def test_user_added_board_reaches_pipeline(self, tmp_db, seed_yaml):
        from engine import pipeline

        pipeline.load_companies()
        watchlist.add("greenhouse", "sifive", name="SiFive")
        slugs = {e.get("slug") for e in pipeline.load_companies()}
        assert "sifive" in slugs
