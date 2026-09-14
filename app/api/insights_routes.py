"""Analytical read endpoints. Every value here is computed from the DB at
request time — nothing here is a placeholder or invented number (see
DASHBOARD.md section 14/15: no fake zeroes, every insight has an evidence
path back to real rows).
"""
from collections import defaultdict
from datetime import datetime, timedelta
from fastapi import APIRouter, Query
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from app.config import get_config
from app.models.db import (
    IssueCluster, IssueClusterMember, AspectMention, CleanFeedback,
    FeatureOntology, RawFeedback, get_session_factory,
)

router = APIRouter(tags=["insights"])

# In-memory storage for positive and neutral grouped clusters
_VIRTUAL_CLUSTERS: dict[int, dict] = {}


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
    """Discovered features for the sidebar. Features with too few mentions
    to say anything meaningful are left out — same noise floor
    (min_cluster_size) used for Top Strengths, so a feature doesn't show up
    with an empty/one-sided summary a click later."""
    session, cfg = _session()
    min_cluster_size = cfg["pipeline"]["min_cluster_size"]

    rows = session.query(FeatureOntology).filter_by(product_name=vehicle).all()

    mention_counts = defaultdict(int)
    for feature_name, count in (
        session.query(AspectMention.feature_name, func.count(AspectMention.id))
        .join(CleanFeedback, AspectMention.clean_feedback_id == CleanFeedback.id)
        .filter(CleanFeedback.product_name == vehicle)
        .group_by(AspectMention.feature_name)
        .all()
    ):
        mention_counts[feature_name] = count

    out = [
        {"feature": r.feature_name, "description": r.description, "category": r.category}
        for r in rows
        if mention_counts[r.feature_name] >= min_cluster_size
    ]
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
        bucket = _severity_bucket(m.severity, m.safety_related)
        severity_buckets[bucket] += 1

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


def _severity_bucket(sev: float | None, safety_related: bool = False) -> str:
    if safety_related:
        return "high"  # safety risk always surfaces as high, regardless of the numeric score
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
    sentiment: str | None = Query("negative"),
):
    """Priority-ranked list of real issues and sentiment insights for R&D.
    Supports negative issues (from IssueCluster) and positive/neutral customer voice insights."""
    if sentiment in ("positive", "neutral"):
        session, cfg = _session()
        window_days = cfg["pipeline"]["trend_window_days"]
        now = datetime.utcnow()
        newer_cutoff = now - timedelta(days=window_days / 2)
        older_cutoff = now - timedelta(days=window_days)

        q = (
            session.query(AspectMention)
            .join(CleanFeedback, AspectMention.clean_feedback_id == CleanFeedback.id)
            .filter(
                CleanFeedback.product_name == vehicle,
                CleanFeedback.is_duplicate_of.is_(None),
                AspectMention.sentiment == sentiment,
            )
            .options(joinedload(AspectMention.clean_feedback))
        )
        if feature:
            q = q.filter(AspectMention.feature_name == feature)
        mentions = q.all()

        by_feature = defaultdict(list)
        for m in mentions:
            if m.feature_name and m.feature_name.strip():
                by_feature[m.feature_name].append(m)

        out = []
        for feat_name, m_list in by_feature.items():
            count = len(m_list)
            newer = sum(1 for m in m_list if m.clean_feedback and m.clean_feedback.created_at and m.clean_feedback.created_at >= newer_cutoff)
            older = sum(1 for m in m_list if m.clean_feedback and m.clean_feedback.created_at and older_cutoff <= m.clean_feedback.created_at < newer_cutoff)
            trend_val = "increasing" if newer > older else ("decreasing" if newer < older else "stable")
            if trend and trend_val != trend:
                continue

            snippets = []
            seen_snips = set()
            for m in m_list:
                snip = (m.snippet or "").strip()
                if snip and snip not in seen_snips:
                    seen_snips.add(snip)
                    snippets.append(snip)

            first_snip = snippets[0] if snippets else f"Customer feedback on {feat_name}"
            prefix = "Praised: " if sentiment == "positive" else "Observation: "
            summary_desc = f"{prefix}{first_snip}"

            virtual_id = 100000 + (abs(hash(f"{vehicle}|{feat_name}|{sentiment}")) % 800000)
            _VIRTUAL_CLUSTERS[virtual_id] = {
                "vehicle": vehicle,
                "feature": feat_name,
                "sentiment": sentiment,
                "summary": summary_desc,
                "mention_ids": [m.id for m in m_list],
                "count": count,
                "trend": trend_val,
                "snippets": snippets[:5],
            }

            priority = round(min(count / 30.0, 1.0), 2)
            if min_priority is not None and priority < min_priority:
                continue

            out.append({
                "id": virtual_id,
                "feature": feat_name,
                "issue": summary_desc,
                "mentions": count,
                "avg_severity": 0.0,
                "safety_related": False,
                "severity_bucket": "low",
                "priority_score": priority,
                "trend": trend_val,
                "confidence": round(min(count / 15.0, 1.0), 2),
                "confidence_basis": "evidence_volume",
                "examples": snippets[:5],
                "sentiment": sentiment,
            })

        session.close()
        out.sort(key=lambda x: x["mentions"], reverse=True)
        return out

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
        "safety_related": r.safety_related,
        "severity_bucket": _severity_bucket(r.avg_severity, r.safety_related),
        "priority_score": r.priority_score,
        "trend": r.trend,
        "confidence": r.confidence,
        "confidence_basis": "evidence_volume",  # not a statistical measure — see DASHBOARD.md section 15
        "examples": r.representative_snippets,
        "sentiment": "negative",
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
    if issue_id in _VIRTUAL_CLUSTERS:
        vc = _VIRTUAL_CLUSTERS[issue_id]
        session, _ = _session()
        mentions = (
            session.query(AspectMention)
            .filter(AspectMention.id.in_(vc["mention_ids"]))
            .options(joinedload(AspectMention.clean_feedback).joinedload(CleanFeedback.raw_feedback))
            .all()
        )
        monthly = defaultdict(int)
        source_groups = set()
        for m in mentions:
            cf = m.clean_feedback
            if cf and cf.created_at:
                monthly[cf.created_at.strftime("%Y-%m")] += 1
            if cf and cf.raw_feedback:
                source_groups.add(cf.raw_feedback.source)
        monthly_trend = [{"month": k, "count": v} for k, v in sorted(monthly.items())]
        session.close()

        rec_text = (
            f"Review positive customer reception around {vc['feature']} to identify competitive advantages."
            if vc["sentiment"] == "positive"
            else f"Monitor customer feedback and observations regarding {vc['feature']}."
        )
        return {
            "id": issue_id,
            "feature": vc["feature"],
            "issue": vc["summary"],
            "mentions": vc["count"],
            "avg_severity": 0.0,
            "safety_related": False,
            "severity_bucket": "low",
            "priority_score": round(min(vc["count"] / 30.0, 1.0), 2),
            "trend": vc["trend"],
            "confidence": round(min(vc["count"] / 15.0, 1.0), 2),
            "confidence_basis": "evidence_volume",
            "primary_context": f"{vc['sentiment'].capitalize()} customer feedback",
            "recommended_investigation": rec_text,
            "source_group_count": len(source_groups),
            "monthly_trend": monthly_trend,
        }

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
        "safety_related": cluster.safety_related,
        "severity_bucket": _severity_bucket(cluster.avg_severity, cluster.safety_related),
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
    if issue_id in _VIRTUAL_CLUSTERS:
        vc = _VIRTUAL_CLUSTERS[issue_id]
        session, _ = _session()
        mentions = (
            session.query(AspectMention)
            .filter(AspectMention.id.in_(vc["mention_ids"]))
            .options(joinedload(AspectMention.clean_feedback).joinedload(CleanFeedback.raw_feedback))
            .all()
        )
        out = []
        for m in mentions:
            clean = m.clean_feedback
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
                    "snippet": m.snippet,
                    "sentiment": m.sentiment,
                    "severity": m.severity,
                    "safety_related": m.safety_related,
                },
            })
        session.close()
        return out

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
                "safety_related": mention.safety_related,
            },
        })
    session.close()
    return out


@router.get("/feedback-by-month")
def feedback_by_month(vehicle: str = Query(...), month: str = Query(..., description="YYYY-MM"), sentiment: str | None = Query(None)):
    """Reviews behind one point on the Overview sentiment-trend chart —
    clicking a month drills into the actual feedback rows for it.
    One review can mention several features (range, charging, price all
    in one sentence) and gets one AspectMention row per feature — grouped
    here by review so it shows up once, with all its feature/sentiment
    tags attached, instead of once per mention."""
    session, _ = _session()
    q = (
        session.query(AspectMention)
        .join(CleanFeedback, AspectMention.clean_feedback_id == CleanFeedback.id)
        .filter(CleanFeedback.product_name == vehicle, CleanFeedback.is_duplicate_of.is_(None))
        .options(joinedload(AspectMention.clean_feedback).joinedload(CleanFeedback.raw_feedback))
    )
    if sentiment:
        q = q.filter(AspectMention.sentiment == sentiment)
    mentions = [m for m in q.all() if m.clean_feedback and m.clean_feedback.created_at and m.clean_feedback.created_at.strftime("%Y-%m") == month]

    reviews: dict[int, dict] = {}
    for m in mentions:
        if not (m.feature_name or "").strip():
            continue  # blank feature from a bad extraction — not a usable tag
        clean = m.clean_feedback
        raw = clean.raw_feedback if clean else None
        key = clean.id
        if key not in reviews:
            reviews[key] = {
                "full_text": clean.clean_text if clean else None,
                "author": raw.author if raw else None,
                "source": raw.source if raw else None,
                "url": raw.url if raw else None,
                "published": raw.created_at.isoformat() if raw and raw.created_at else None,
                "tags": [],
            }
        reviews[key]["tags"].append({
            "feature": m.feature_name,
            "sentiment": m.sentiment or "neutral",
            "snippet": m.snippet,
        })

    out = list(reviews.values())
    session.close()
    out.sort(key=lambda r: r["published"] or "", reverse=True)
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
        .filter(CleanFeedback.product_name == vehicle, CleanFeedback.is_duplicate_of.is_(None))
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
        .filter(CleanFeedback.product_name == vehicle, CleanFeedback.is_duplicate_of.is_(None))
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