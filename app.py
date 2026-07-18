"""Entrypoint: python app.py -> http://127.0.0.1:8000"""
from dotenv import load_dotenv

load_dotenv()

import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("web.main:app", host="127.0.0.1", port=port)
