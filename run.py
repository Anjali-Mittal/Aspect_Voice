"""Single entrypoint for local dev and vendor deployment alike.
Host/port come only from .env (or the vendor's injected PORT var) — never
hardcoded, so there's no port clash between this and anything else running.

Local:   python run.py
Vendor:  same command — most PaaS vendors (Render, Railway, Fly) run this
         directly and inject their own PORT into the environment, which
         get_server_settings() picks up automatically.
"""
import uvicorn
from app.config import get_server_settings

if __name__ == "__main__":
    settings = get_server_settings()
    uvicorn.run("app.main:app", host=settings["host"], port=settings["port"], reload=False)
