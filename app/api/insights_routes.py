"""Analytical read endpoints. Every value here is computed from the DB at
request time — nothing here is a placeholder or invented number (see
DASHBOARD.md section 14/15: no fake zeroes, every insight has an evidence
path back to real rows).
"""
from collections import defaultdict
from fastapi import APIRouter, Query
from sqlalchemy.orm import joinedload
from app.config import get_config
from app.models.db import (
    IssueCluster, IssueClusterMember, AspectMention, CleanFeedback,
    FeatureOntology, RawFeedback, get_session_factory,
)

router = APIRouter(tags=["insights"])


def _session():
    cfg = get_config()
    Session = get_session_factory(cfg["storage"]["db_url"])
    return Session(), cfg


@router.get("/vehicles")
def list_vehicles():
    """Vehicles actually present in the data — not a hardcoded catalogue.
    Selector in the frontend is populated from this, per DASHBOARD.md
    section 2: identity is configured, but what shows up is what was
    actually ingested."""
    session, _ = _session()
    rows = session.query(RawFeedback.product_name).distinct().all()
    session.close()
    return [r[0] for r in rows]


@router.get("/features")
def list_features(vehicle: str = Query(...)):
    session, _ = _session()
    rows = session.query(FeatureOntology).filter_by(product_name=vehicle).all()
    out = [{"feature": r.feature_name, "description": r.description} for r in rows]
    session.close()
    return out


@router.get("/features/{feature_name}/summary")
def feature_summary(feature_name: str, vehicle: str = Query(...)):
    """Per-feature detail view — DASHBOARD.md section 5.2. Mentions,
    sentiment split, severity split, all computed from AspectMention rows
    for this feature+vehicle, not stored/cached separately."""
    session, _ = _session()
    mentions = (
        session.query(AspectMention)
        .join(CleanFeedback, AspectMention.clean_feedback_id == CleanFeedback.id)
        .filter(AspectMention.feature_name == feature_name, CleanFeedback.product_name == vehicle)
        .all()
    )
    session.close()

    if not mentions:
        return {"feature": feature_name, "mentions": 0, "note": "no data yet for this feature"}

    total = len(mentions)
    sentiment_counts = defaultdict(int)
    severity_buckets = {"high": 0, "medium": 0, "low": 0}
    for m in mentions:
        sentiment_counts[m.sentiment or "neutral"] += 1
        sev = m.severity or 0
        if sev >= 0.66:
            severity_buckets["high"] += 1
        elif sev >= 0.33:
            severity_buckets["medium"] += 1
        else:
            severity_buckets["low"] += 1

    return {
        "feature": feature_name,
        "mentions": total,
        "sentiment_pct": {
            "positive": round(100 * sentiment_counts["positive"] / total, 1),
            "neutral": round(100 * sentiment_counts["neutral"] / total, 1),
            "negative": round(100 * sentiment_counts["negative"] / total, 1),
        },
        "severity_pct": {
            k: round(100 * v / total, 1) for k, v in severity_buckets.items()
        },
    }


def _severity_bucket(sev: float | None) -> str:
    sev = sev or 0
    if sev >= 0.66:
        return "high"
    if sev >= 0.33:
        return "medium"
    return "low"


@router.get("/issues")
def list_issues(
    vehicle: str = Query(...),
    feature: str | None = Query(None),
    trend: str | None = Query(None),
    severity: str | None = Query(None),
    min_priority: float | None = Query(None),
):
    """Priority-ranked list of real issues for R&D. Filters — DASHBOARD.md
    section 8 — are applied server-side so the frontend never has to
    reimplement ranking/filtering logic (section 12)."""
    session, _ = _session()
    q = session.query(IssueCluster).filter_by(product_name=vehicle)
    if feature:
        q = q.filter(IssueCluster.feature_name == feature)
    if trend:
        q = q.filter(IssueCluster.trend == trend)
    if min_priority is not None:
        q = q.filter(IssueCluster.priority_score >= min_priority)
    rows = q.order_by(IssueCluster.priority_score.desc()).all()

    out = [{
        "id": r.id,
        "feature": r.feature_name,
        "issue": r.issue_summary,
        "mentions": r.mention_count,
        "avg_severity": r.avg_severity,
        "severity_bucket": _severity_bucket(r.avg_severity),
        "priority_score": r.priority_score,
        "trend": r.trend,
        "confidence": r.confidence,
        "confidence_basis": "evidence_volume",  # not a statistical measure — see DASHBOARD.md section 15
        "examples": r.representative_snippets,
    } for r in rows]

    if severity:
        out = [o for o in out if o["severity_bucket"] == severity]

    session.close()
    return out


@router.get("/issues/{issue_id}")
def issue_detail(issue_id: int):
    """Full cluster detail for the Priority / R&D view and the Evidence
    Explorer header — DASHBOARD.md section 7 and 9.1. Includes the monthly
    mention-count trend used for the evidence trend bar chart."""
    session, _ = _session()
    cluster = session.query(IssueCluster).filter_by(id=issue_id).first()
    if cluster is None:
        session.close()
        return {"error": "not found"}

    members = session.query(IssueClusterMember).filter_by(issue_cluster_id=issue_id).all()
    monthly = defaultdict(int)
    source_groups = set()
    for member in members:
        cf = member.aspect_mention.clean_feedback if member.aspect_mention else None
        if cf and cf.created_at:
            monthly[cf.created_at.strftime("%Y-%m")] += 1
        if cf and cf.raw_feedback:
            source_groups.add(cf.raw_feedback.source)
    monthly_trend = [{"month": m, "count": c} for m, c in sorted(monthly.items())]
    source_group_count = len(source_groups)

    session.close()
    return {
        "id": cluster.id,
        "feature": cluster.feature_name,
        "issue": cluster.issue_summary,
        "mentions": cluster.mention_count,
        "avg_severity": cluster.avg_severity,
        "severity_bucket": _severity_bucket(cluster.avg_severity),
        "priority_score": cluster.priority_score,
        "trend": cluster.trend,
        "confidence": cluster.confidence,
        "confidence_basis": "evidence_volume",  # not a statistical measure — see DASHBOARD.md section 15
        "primary_context": cluster.primary_context,
        "recommended_investigation": cluster.recommended_investigation,
        "source_group_count": source_group_count,
        "monthly_trend": monthly_trend,
    }


@router.get("/issues/{issue_id}/evidence")
def issue_evidence(issue_id: int):
    """Full evidence chain for one issue cluster — every source review/comment
    that fed it, not just the top-5 representative snippets. Distinguishes
    Observed (raw text) from AI Interpretation (sentiment/severity/snippet)
    per DASHBOARD.md section 9.2."""
    session, _ = _session()
    members = (
        session.query(IssueClusterMember)
        .filter_by(issue_cluster_id=issue_id)
        .all()
    )
    out = []
    for member in members:
        mention = member.aspect_mention
        clean = mention.clean_feedback
        raw = clean.raw_feedback if clean else None
        out.append({
            "observed": {
                "full_text": clean.clean_text if clean else None,
                "author": raw.author if raw else None,
                "source": raw.source if raw else None,
                "url": raw.url if raw else None,
                "published": raw.created_at.isoformat() if raw and raw.created_at else None,
            },
            "ai_interpretation": {
                "snippet": mention.snippet,
                "sentiment": mention.sentiment,
                "severity": mention.severity,
            },
        })
    session.close()
    return out


@router.get("/overview")
def overview(vehicle: str = Query(...)):
    """Everything the Product Overview page needs in one call — KPIs,
    sentiment trend, top strengths, top pain points, emerging issues.
    DASHBOARD.md section 3. All computed live from real rows; if a section
    has no data yet, it comes back empty (never a fabricated number) — see
    DASHBOARD.md section 14."""
    session, cfg = _session()
    high_priority_threshold = cfg["pipeline"]["high_priority_threshold"]
    min_cluster_size = cfg["pipeline"]["min_cluster_size"]

    clean_count = (
        session.query(CleanFeedback)
        .filter(CleanFeedback.product_name == vehicle, CleanFeedback.is_duplicate_of.is_(None))
        .count()
    )

    mentions = (
        session.query(AspectMention)
        .join(CleanFeedback, AspectMention.clean_feedback_id == CleanFeedback.id)
        .filter(CleanFeedback.product_name == vehicle)
        .options(joinedload(AspectMention.clean_feedback))
        .all()
    )
    total_mentions = len(mentions)
    sentiment_counts = defaultdict(int)
    for m in mentions:
        sentiment_counts[m.sentiment or "neutral"] += 1

    features = session.query(FeatureOntology).filter_by(product_name=vehicle).all()
    issues = (
        session.query(IssueCluster)
        .filter_by(product_name=vehicle)
        .order_by(IssueCluster.priority_score.desc())
        .all()
    )
    high_priority = [i for i in issues if (i.priority_score or 0) >= high_priority_threshold]
    emerging = [i for i in issues if i.trend == "increasing"]

    # top strengths: per-feature positive ratio, among features with enough
    # mentions to be meaningful (reuses min_cluster_size as the noise floor)
    by_feature = defaultdict(lambda: defaultdict(int))
    for m in mentions:
        by_feature[m.feature_name][m.sentiment or "neutral"] += 1

    strengths = []
    for feature_name, counts in by_feature.items():
        total = sum(counts.values())
        if total < min_cluster_size:
            continue
        pos_pct = 100 * counts.get("positive", 0) / total
        strengths.append({"feature": feature_name, "positive_pct": round(pos_pct, 1), "mentions": total})
    strengths.sort(key=lambda s: s["positive_pct"], reverse=True)

    # sentiment trend by month
    monthly = defaultdict(lambda: defaultdict(int))
    for m in mentions:
        cf = m.clean_feedback
        if not cf or not cf.created_at:
            continue
        month_key = cf.created_at.strftime("%Y-%m")
        monthly[month_key][m.sentiment or "neutral"] += 1
    trend_series = [
        {"month": month, "positive": v.get("positive", 0), "neutral": v.get("neutral", 0), "negative": v.get("negative", 0)}
        for month, v in sorted(monthly.items())
    ]

    session.close()

    return {
        "vehicle": vehicle,
        "kpis": {
            "feedback_analyzed": clean_count,
            "sentiment_pct": {
                "positive": round(100 * sentiment_counts["positive"] / total_mentions, 1) if total_mentions else 0,
                "neutral": round(100 * sentiment_counts["neutral"] / total_mentions, 1) if total_mentions else 0,
                "negative": round(100 * sentiment_counts["negative"] / total_mentions, 1) if total_mentions else 0,
            },
            "discovered_features": len(features),
            "recurring_issues": len(issues),
            "high_priority_issues": len(high_priority),
            "emerging_issues": len(emerging),
        },
        "sentiment_trend": trend_series,
        "top_strengths": strengths[:5],
        "top_pain_points": [{
            "id": i.id, "feature": i.feature_name, "issue": i.issue_summary,
            "mentions": i.mention_count, "priority_score": i.priority_score, "trend": i.trend,
        } for i in issues[:5]],
        "emerging_issues": [{
            "id": i.id, "feature": i.feature_name, "issue": i.issue_summary, "trend": i.trend,
        } for i in emerging],
    }


@router.get("/stats")
def stats(vehicle: str = Query(...)):
    session, _ = _session()
    total = session.query(RawFeedback).filter_by(product_name=vehicle).count()
    relevant = session.query(RawFeedback).filter_by(product_name=vehicle, is_relevant=1).count()
    clean = (
        session.query(CleanFeedback)
        .filter(CleanFeedback.product_name == vehicle, CleanFeedback.is_duplicate_of.is_(None))
        .count()
    )
    duplicates = (
        session.query(CleanFeedback)
        .filter(CleanFeedback.product_name == vehicle, CleanFeedback.is_duplicate_of.isnot(None))
        .count()
    )
    mentions = (
        session.query(AspectMention)
        .join(CleanFeedback, AspectMention.clean_feedback_id == CleanFeedback.id)
        .filter(CleanFeedback.product_name == vehicle)
        .count()
    )
    clusters = session.query(IssueCluster).filter_by(product_name=vehicle).count()
    session.close()
    return {
        "total_raw": total,
        "relevant": relevant,
        "clean": clean,
        "fuzzy_duplicates": duplicates,
        "aspect_mentions": mentions,
        "issue_clusters": clusters,
    }
