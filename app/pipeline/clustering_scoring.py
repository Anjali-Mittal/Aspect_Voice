import logging
from datetime import datetime, timedelta
from collections import defaultdict
from sqlalchemy.orm import joinedload
from app.config import get_config
from app.models.db import AspectMention, CleanFeedback, IssueCluster, IssueClusterMember, get_session_factory
from app.llm.client import call_llm_json

logger = logging.getLogger(__name__)

CLUSTER_PROMPT = """Feature: {feature_name}
Below are {n} numbered negative customer snippets all about this one feature.
Group them into distinct real issues (e.g. two snippets might both be
negative about "braking" but one is about squeaky sound and another about
weak stopping power -- those are different issues, keep them separate).

For each issue, also provide:
- primary_context: a short phrase (3-6 words) for the riding/usage context
  this issue mostly comes up in, if the snippets make that clear (e.g.
  "Long-distance / pillion riding", "City traffic braking"). Leave empty
  string if the snippets don't support a specific context.
- recommended_investigation: one sentence suggesting what a product/R&D team
  could look into. This is decision support, not a diagnosis -- do not claim
  it proves an engineering defect, just suggest where to look.

Return JSON:
{{"issues": [{{"summary": "...", "member_indices": [0,2,5], "primary_context": "...", "recommended_investigation": "..."}}, ...]}}

Snippets:
{snippets}
"""

# Below this many members, a cluster's time-bucket split is too thin to call
# a direction on — flagged "insufficient_data" rather than guessing.
MIN_MEMBERS_FOR_TREND = 6
# Below this many total reviews (for the product) in either half of the
# window, a rate computed against that half is just noise.
MIN_PRODUCT_VOLUME_FOR_TREND = 10


def _compute_trend(members, window_days: int, total_newer: int, total_older: int) -> str:
    """Splits the trend window into two equal halves and compares each
    half's mention count as a SHARE of all reviews for the product in that
    half — not a raw count. Without that normalization, a scraping run
    that happened to pull more from recent months than old ones makes
    every issue look 'increasing' regardless of whether the complaint
    rate actually rose. Still a plain comparison of two numbers with a
    fixed multiplier, not a statistical test — deliberately simple and
    inspectable, just measuring the right thing now."""
    if len(members) < MIN_MEMBERS_FOR_TREND:
        return "insufficient_data"
    if total_newer < MIN_PRODUCT_VOLUME_FOR_TREND or total_older < MIN_PRODUCT_VOLUME_FOR_TREND:
        return "insufficient_data"

    now = datetime.utcnow()
    half = window_days / 2
    newer_cutoff = now - timedelta(days=half)
    older_cutoff = now - timedelta(days=window_days)

    newer = older = 0
    undated = 0
    for m in members:
        ts = m.clean_feedback.created_at if m.clean_feedback else None
        if ts is None:
            undated += 1
            continue
        if ts >= newer_cutoff:
            newer += 1
        elif ts >= older_cutoff:
            older += 1
        # older than the full window doesn't count toward either half

    if newer + older < MIN_MEMBERS_FOR_TREND:
        return "insufficient_data"

    rate_newer = newer / total_newer
    rate_older = older / total_older
    if rate_newer > rate_older * 1.3:
        return "increasing"
    if rate_older > rate_newer * 1.3:
        return "decreasing"
    return "stable"


def _compute_confidence(mention_count: int) -> float:
    """Evidence-volume proxy, not a statistical confidence interval — more
    supporting mentions = more confidence the issue is real, capped at 1.0.
    Documented as such wherever it's surfaced (see /overview, DASHBOARD spec
    section 15 trust requirements) so it's never mistaken for a p-value."""
    return round(min(mention_count / 15, 1.0), 2)


def run_clustering_and_scoring():
    cfg = get_config()
    Session = get_session_factory(cfg["storage"]["db_url"])
    window_days = cfg["pipeline"]["trend_window_days"]
    min_cluster_size = cfg["pipeline"]["min_cluster_size"]

    # Short-lived session for this one read, then closed — same reasoning
    # as aspect_extraction.py: a connection held open across the whole
    # multi-feature, multi-LLM-call run is what Neon's serverless Postgres
    # was killing mid-request.
    with Session() as session:
        negatives = (
            session.query(AspectMention)
            .filter(AspectMention.sentiment == "negative")
            .options(joinedload(AspectMention.clean_feedback))  # loaded upfront — session closes right after this block, and clean_feedback is read later (trend calc, snippets) after that
            .all()
        )
        already_clustered_ids = {
            row[0] for row in session.query(IssueClusterMember.aspect_mention_id).all()
        }

    if not negatives:
        return {"clusters": 0, "note": "no negative mentions yet"}

    by_product_feature = defaultdict(lambda: defaultdict(list))
    for m in negatives:
        if not m.clean_feedback:
            continue
        by_product_feature[m.clean_feedback.product_name][m.feature_name].append(m)

    total_clusters = 0
    skipped_features = {}  # "product | feature" -> reason, surfaced in the return value
    unchanged_features = []  # features with no new mentions — persisted as-is
    now = datetime.utcnow()

    total_features = sum(len(f) for f in by_product_feature.values())
    feature_num = 0

    # Per-product review-volume totals for the trend denominator — one
    # pair of quick counts per product (not per feature), reused across
    # every feature of that product.
    newer_cutoff = now - timedelta(days=window_days / 2)
    older_cutoff = now - timedelta(days=window_days)
    product_volume = {}
    with Session() as session:
        for product_name in by_product_feature:
            total_newer = (
                session.query(CleanFeedback)
                .filter(CleanFeedback.product_name == product_name, CleanFeedback.is_duplicate_of.is_(None),
                        CleanFeedback.created_at >= newer_cutoff)
                .count()
            )
            total_older = (
                session.query(CleanFeedback)
                .filter(CleanFeedback.product_name == product_name, CleanFeedback.is_duplicate_of.is_(None),
                        CleanFeedback.created_at >= older_cutoff, CleanFeedback.created_at < newer_cutoff)
                .count()
            )
            product_volume[product_name] = (total_newer, total_older)

    for product_name, by_feature in by_product_feature.items():
        total_newer, total_older = product_volume[product_name]
        for feature_name, mentions in by_feature.items():
            feature_num += 1
            skip_key = f"{product_name} | {feature_name}"

            has_new_mentions = any(m.id not in already_clustered_ids for m in mentions)
            if not has_new_mentions:
                unchanged_features.append(skip_key)
                continue

            if len(mentions) < min_cluster_size:
                skipped_features[skip_key] = (
                    f"only {len(mentions)} negative mentions, need {min_cluster_size}"
                )
                continue

            print(f"[cluster-score] ({feature_num}/{total_features}) {product_name}: '{feature_name}' — clustering {len(mentions)} mentions...", flush=True)

            snippets = "\n".join(
                f"{j}. {m.snippet or m.clean_feedback.clean_text[:200]}" for j, m in enumerate(mentions)
            )
            prompt = CLUSTER_PROMPT.format(feature_name=feature_name, n=len(mentions), snippets=snippets)
            try:
                result = call_llm_json(prompt)
            except Exception as e:
                print(f"[cluster-score] ({feature_num}/{total_features}) {product_name}: '{feature_name}' FAILED — {str(e)[:150]}", flush=True)
                skipped_features[skip_key] = f"LLM call failed: {e}"
                continue

            issues_in = result.get("issues", [])
            malformed = [i for i in issues_in if not isinstance(i, dict)]
            if malformed:
                logger.warning(
                    "clustering: LLM returned %d non-dict issue entries for product=%s feature=%s, dropping them: %r",
                    len(malformed), product_name, feature_name, malformed[:3],
                )
            issues_in = [i for i in issues_in if isinstance(i, dict)]
            if not issues_in:
                skipped_features[skip_key] = "LLM returned zero usable issues for this feature"

            new_clusters = []  # (IssueCluster, [member AspectMention,...])
            for issue in issues_in:
                raw_indices = issue.get("member_indices", [])
                members = [mentions[idx] for idx in raw_indices if isinstance(idx, int) and 0 <= idx < len(mentions)]
                if len(members) < min_cluster_size:
                    logger.warning(
                        "clustering: dropped issue '%s' for product=%s feature=%s — only %d members, need %d",
                        issue.get("summary", ""), product_name, feature_name, len(members), min_cluster_size,
                    )
                    continue

                avg_severity = sum(m.severity or 0 for m in members) / len(members)
                safety_related = any(m.safety_related for m in members)

                recent_count = sum(
                    1 for m in members
                    if m.clean_feedback and m.clean_feedback.created_at
                    and m.clean_feedback.created_at >= now - timedelta(days=window_days)
                )
                recency_boost = recent_count / len(members)

                # deterministic scoring formula: volume + severity + recency trend
                priority_score = (
                    0.4 * min(len(members) / 20, 1.0)
                    + 0.4 * avg_severity
                    + 0.2 * recency_boost
                )

                cluster = IssueCluster(
                    product_name=product_name,
                    feature_name=feature_name,
                    issue_summary=issue.get("summary", ""),
                    mention_count=len(members),
                    avg_severity=round(avg_severity, 3),
                    safety_related=safety_related,
                    priority_score=round(priority_score, 3),
                    trend=_compute_trend(members, window_days, total_newer, total_older),
                    confidence=_compute_confidence(len(members)),
                    primary_context=issue.get("primary_context") or None,
                    recommended_investigation=issue.get("recommended_investigation") or None,
                    representative_snippets=[m.snippet for m in members[:5]],
                )
                new_clusters.append((cluster, members))

            # Fresh short-lived session for just this feature's write —
            # delete its old clusters and insert the new ones in one
            # transaction, then close immediately. A crash here only
            # loses this one feature's rebuild, not the whole run.
            with Session() as write_session:
                old_cluster_ids = [
                    c.id for c in write_session.query(IssueCluster.id)
                    .filter_by(product_name=product_name, feature_name=feature_name)
                ]
                if old_cluster_ids:
                    write_session.query(IssueClusterMember).filter(
                        IssueClusterMember.issue_cluster_id.in_(old_cluster_ids)
                    ).delete(synchronize_session=False)
                    write_session.query(IssueCluster).filter_by(
                        product_name=product_name, feature_name=feature_name
                    ).delete()

                for cluster, members in new_clusters:
                    write_session.add(cluster)
                    write_session.flush()  # need cluster.id for the membership rows below
                    for m in members:
                        write_session.add(IssueClusterMember(issue_cluster_id=cluster.id, aspect_mention_id=m.id))
                    total_clusters += 1

                write_session.commit()

            print(f"[cluster-score] ({feature_num}/{total_features}) {product_name}: '{feature_name}' done, +{len(new_clusters)} clusters", flush=True)

    return {
        "clusters": total_clusters,
        "skipped_features": skipped_features,
        "unchanged_features": unchanged_features,
    }