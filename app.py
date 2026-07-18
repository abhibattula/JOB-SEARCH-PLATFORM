"""Entrypoint: python app.py -> http://127.0.0.1:8000

Set SCHEDULE_REFRESH=1 in .env to also run an automatic nightly refresh
(07:00 local) while the app is up.
"""
from dotenv import load_dotenv

load_dotenv()

import os

import uvicorn

if __name__ == "__main__":
    if os.environ.get("SCHEDULE_REFRESH") == "1":
        from apscheduler.schedulers.background import BackgroundScheduler

        from engine import pipeline

        scheduler = BackgroundScheduler()
        scheduler.add_job(
            lambda: pipeline.run_refresh("scheduled", force=True),
            "cron",
            hour=7,
            minute=0,
        )
        scheduler.start()

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("web.main:app", host="127.0.0.1", port=port)
