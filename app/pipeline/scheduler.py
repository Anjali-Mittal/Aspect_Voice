"""Monthly auto-run of the full pipeline — with no paid Render cron service,
no card on file anywhere.

How it actually runs on Render's free tier:
Render's free web-service tier has no free cron job type of its own (cron
jobs there bill per-minute). So instead: a free external pinger
(cron-job.org — no card, see DEPLOYMENT.md) hits this app's
/pipeline/scheduled-trigger endpoint on a short interval (e.g. daily).
Each ping is cheap — it's just a DB timestamp check — and does nothing
unless a full interval has actually elapsed. That elapsed-time check lives
here, not in the external pinger, so the "once a month" guarantee doesn't
depend on the pinger's schedule being exact.
"""
from datetime import datetime, timedelta
from app.config import get_config
from app.models.db import PipelineRunLog, get_session_factory


def is_due(session) -> bool:
    cfg = get_config()
    sched = cfg.get("schedule", {})
    if not sched.get("enabled", True):
        return False
    interval_days = sched.get("interval_days", 30)

    last_scheduled = (
        session.query(PipelineRunLog)
        .filter_by(trigger="scheduled")
        .order_by(PipelineRunLog.started_at.desc())
        .first()
    )
    if last_scheduled is None:
        return True
    return datetime.utcnow() - last_scheduled.started_at >= timedelta(days=interval_days)


def run_if_due() -> dict:
    """Call from the /pipeline/scheduled-trigger endpoint. Runs the full
    pipeline only if the configured interval has actually elapsed; otherwise
    a cheap no-op. Logs every scheduled run (attempted or actual) so
    /pipeline/schedule-status gives an honest, checkable history."""
    # imported here, not at module top, to avoid a circular import with main.py
    from app.pipeline.ingest import run_ingestion
    from app.pipeline.relevance_filter import run_relevance_filter
    from app.pipeline.cleaning import run_cleaning
    from app.pipeline.ontology_discovery import run_ontology_discovery
    from app.pipeline.aspect_extraction import run_aspect_extraction
    from app.pipeline.clustering_scoring import run_clustering_and_scoring

    cfg = get_config()
    Session = get_session_factory(cfg["storage"]["db_url"])
    session = Session()

    if not is_due(session):
        session.close()
        return {"ran": False, "reason": "not due yet"}

    log = PipelineRunLog(trigger="scheduled", started_at=datetime.utcnow())
    session.add(log)
    session.commit()

    results = {}
    try:
        results["ingest"] = run_ingestion()
        results["relevance_filter"] = run_relevance_filter()
        results["cleaning"] = run_cleaning()
        results["ontology_discovery"] = run_ontology_discovery()
        results["aspect_extraction"] = run_aspect_extraction()
        results["cluster_score"] = run_clustering_and_scoring()
    finally:
        log.finished_at = datetime.utcnow()
        log.results = results
        session.commit()
        session.close()

    return {"ran": True, "results": results}
