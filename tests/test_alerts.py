"""004-WS-A: fresh best-match computation, notification gating, seen filter."""
from datetime import datetime, timedelta, timezone

from engine import alerts, db, settings


def seed_scored(url, score, first_seen_days_ago=0.0, entry=True, sponsorship="UNKNOWN"):
    db.upsert_job(
        {"title": f"Job {url}", "company": "TestCo", "url": url, "source": "greenhouse"}
    )
    jobs, _ = db.query_jobs(window=None, statuses=None, entry_level=None,
                            include_ineligible=True)
    job = next(j for j in jobs if j["url"] == url)
    db.set_classification(job["id"], entry, sponsorship, None)
    if score is not None:
        db.set_match(job["id"], score, '{"match_score": %s, "method": "basic"}' % score)
    if first_seen_days_ago:
        stamp = (
            datetime.now(timezone.utc) - timedelta(days=first_seen_days_ago)
        ).strftime("%Y-%m-%d %H:%M:%S.000")
        with db._conn() as conn:
            conn.execute("UPDATE jobs SET first_seen = ? WHERE id = ?", (stamp, job["id"]))
    return job["id"]


def hour_ago():
    return (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
        "%Y-%m-%d %H:%M:%S.000"
    )


class TestSeenFilter:
    def test_seen_since_narrows_to_recent_first_seen(self, tmp_db):
        seed_scored("new", 80)
        seed_scored("old", 90, first_seen_days_ago=3)
        rows, total = db.query_jobs(window=None, seen_since=hour_ago())
        assert total == 1
        assert rows[0]["url"] == "new"


class TestBestMatches:
    def test_computes_only_fresh_eligible_strong_matches(self, tmp_db):
        seed_scored("strong", 85)
        seed_scored("weak", 40)
        seed_scored("stale-strong", 95, first_seen_days_ago=2)
        seed_scored("excluded", 90, sponsorship="EXCLUDED")
        seed_scored("senior", 90, entry=False)
        matches = alerts.new_best_matches(since=hour_ago())
        assert [m["url"] for m in matches] == ["strong"]


class TestNotify:
    def test_sends_when_enabled_and_matches_exist(self, tmp_db, monkeypatch):
        sent = []
        monkeypatch.setattr(alerts, "_send", lambda title, msg: sent.append((title, msg)))
        seed_scored("strong", 85)
        alerts.process(since=hour_ago())
        assert len(sent) == 1
        assert "TestCo" in sent[0][1]

    def test_silent_when_disabled(self, tmp_db, monkeypatch):
        sent = []
        monkeypatch.setattr(alerts, "_send", lambda title, msg: sent.append(1))
        settings.set("ALERTS_ENABLED", "0")
        seed_scored("strong", 85)
        alerts.process(since=hour_ago())
        assert sent == []

    def test_silent_when_no_matches(self, tmp_db, monkeypatch):
        sent = []
        monkeypatch.setattr(alerts, "_send", lambda title, msg: sent.append(1))
        alerts.process(since=hour_ago())
        assert sent == []

    def test_notification_failure_never_raises(self, tmp_db, monkeypatch):
        def boom(title, msg):
            raise RuntimeError("no notification backend")

        monkeypatch.setattr(alerts, "_send", boom)
        seed_scored("strong", 85)
        alerts.process(since=hour_ago())  # must not raise
