from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_server_settings
from app.api import pipeline_routes, insights_routes

app = FastAPI(title="AspectVoice")

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
