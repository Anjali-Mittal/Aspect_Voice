import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_server_settings
from app.api import pipeline_routes, insights_routes

# Windows' default console codepage (cp1252) can't print emoji/surrogate
# characters that show up constantly in scraped reviews — any print() or
# log line containing one crashes the whole process with
# UnicodeEncodeError. Force UTF-8 with replacement instead of raising, so
# a log statement never takes down the server. No-op on Linux/Render,
# where stdout is already UTF-8.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

app = FastAPI(title="Customer Voice Intelligence")

_server = get_server_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_server["cors_origins"] or ["*"],  # set CORS_ORIGINS in .env for prod; "*" is dev-only fallback
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pipeline_routes.router)
app.include_router(insights_routes.router)


@app.get("/health")
def health():
    return {"status": "ok"}