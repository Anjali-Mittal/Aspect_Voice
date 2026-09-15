"""All /pipeline/* routes — triggering stages, manually or on schedule.
Business logic lives in app/pipeline/*, this module only wires HTTP to it.
"""
import os
from fastapi import APIRouter, Header, HTTPException, Query
from app.config import get_config
from app.models.db import PipelineRunLog, get_session_factory
from app.pipeline.ingest import run_ingestion
from app.pipeline.relevance_filter import run_relevance_filter
from app.pipeline.cleaning import run_cleaning
from app.pipeline.ontology_discovery import run_ontology_discovery
from app.pipeline.categorize_features import run_categorize_features
from app.pipeline.aspect_extraction import run_aspect_extraction
from app.pipeline.clustering_scoring import run_clustering_and_scoring
from app.pipeline.scheduler import run_if_due

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

# Optional filter on every stage below — leave blank to run for every
# product in config.targets, or pass one to run that product only
# (e.g. "Ather 450S") without touching data for the others.
ProductFilter = Query(default=None, description="Run for this product_name only (exact match). Omit to run for all products.")


@router.post("/ingest")
def ingest(product_name: str | None = ProductFilter):
    return run_ingestion(product_name)


@router.post("/relevance-filter")
def relevance_filter(product_name: str | None = ProductFilter):
    return run_relevance_filter(product_name)


@router.post("/cleaning")
def cleaning(product_name: str | None = ProductFilter):
    return run_cleaning(product_name)


@router.post("/ontology-discovery")
def ontology_discovery(product_name: str | None = ProductFilter):
    return run_ontology_discovery(product_name)


@router.post("/categorize-features")
def categorize_features(product_name: str | None = ProductFilter):
    return run_categorize_features(product_name)


@router.post("/aspect-extraction")
def aspect_extraction(product_name: str | None = ProductFilter):
    return run_aspect_extraction(product_name)


@router.post("/cluster-score")
def cluster_score(product_name: str | None = ProductFilter):
    return run_clustering_and_scoring(product_name)


@router.post("/run-all")
def run_all(product_name: str | None = ProductFilter):
    """Runs full pipeline end to end, in order. Idempotent — each stage skips
    rows it's already processed, except clustering, which always rebuilds fresh.
    Pass product_name to scope the entire run to one product."""
    results = {}
    results["ingest"] = run_ingestion(product_name)
    results["relevance_filter"] = run_relevance_filter(product_name)
    results["cleaning"] = run_cleaning(product_name)
    results["ontology_discovery"] = run_ontology_discovery(product_name)
    results["categorize_features"] = run_categorize_features(product_name)
    results["aspect_extraction"] = run_aspect_extraction(product_name)
    results["cluster_score"] = run_clustering_and_scoring(product_name)
    return results


@router.post("/scheduled-trigger")
def scheduled_trigger(x_scheduler_secret: str = Header(default="")):
    """Hit by a free external pinger (cron-job.org — see DEPLOYMENT.md) on a
    short interval. Only actually runs the pipeline if a full interval
    (config.schedule.interval_days, default 30) has elapsed since the last
    scheduled run — see app/pipeline/scheduler.py for that check."""
    expected = os.getenv("SCHEDULER_SECRET")
    if not expected or x_scheduler_secret != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing scheduler secret")
    return run_if_due()


@router.get("/schedule-status")
def schedule_status():
    """Honest, checkable history of scheduled runs — not just a claim that
    scheduling exists. Shows every scheduled attempt, whether it actually
    ran or was skipped as not-yet-due, and its results."""
    cfg = get_config()
    Session = get_session_factory(cfg["storage"]["db_url"])
    session = Session()
    rows = (
        session.query(PipelineRunLog)
        .filter_by(trigger="scheduled")
        .order_by(PipelineRunLog.started_at.desc())
        .limit(20)
        .all()
    )
    out = [{
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "results": r.results,
    } for r in rows]
    session.close()
    return {
        "interval_days": cfg.get("schedule", {}).get("interval_days", 30),
        "enabled": cfg.get("schedule", {}).get("enabled", True),
        "history": out,
    }