"""
One-time backfill: snap existing AspectMention.feature_name values to
their nearest FeatureOntology.feature_name (per product), then wipe
IssueCluster / IssueClusterMember rows for any feature whose mentions
changed — clustering_scoring.py rebuilds them cleanly on next run
since it deletes-then-reinserts per (product, feature_name).

Run once, after deploying the aspect_extraction.py fix.

Usage:
    python -m scripts.backfill_fix_feature_names --dry-run
    python -m scripts.backfill_fix_feature_names --apply
"""

import argparse
from collections import defaultdict
from rapidfuzz import process, fuzz

from app.config import get_config
from app.models.db import (
    FeatureOntology, AspectMention, CleanFeedback, IssueCluster, IssueClusterMember,
    get_session_factory,
)
from sqlalchemy.orm import joinedload

FEATURE_MATCH_THRESHOLD = 80


def snap(raw_feature: str, ontology_names: list[str]) -> str:
    if not ontology_names:
        return raw_feature
    match = process.extractOne(raw_feature, ontology_names, scorer=fuzz.token_sort_ratio)
    if match and match[1] >= FEATURE_MATCH_THRESHOLD:
        return match[0]
    return raw_feature


def main(apply: bool):
    cfg = get_config()
    Session = get_session_factory(cfg["storage"]["db_url"])
    session = Session()

    print("loading ontology + mentions...")
    ontologies = session.query(FeatureOntology).all()
    ontology_by_product = defaultdict(list)
    for f in ontologies:
        ontology_by_product[f.product_name].append(f.feature_name)

    mentions = (
        session.query(AspectMention)
        .join(CleanFeedback, AspectMention.clean_feedback_id == CleanFeedback.id)
        .options(joinedload(AspectMention.clean_feedback))  # was lazy-loading per row —
        # one DB round-trip per mention (N+1), which is what actually hangs for minutes
        .all()
    )
    print(f"loaded {len(mentions)} mentions, checking against {len(ontologies)} ontology rows...")

    changed_pairs = set()  # (product_name, old_feature_name) -> needs re-cluster
    updates = 0

    for idx, m in enumerate(mentions):
        if idx and idx % 500 == 0:
            print(f"  ...{idx}/{len(mentions)} checked")
        product_name = m.clean_feedback.product_name
        names = ontology_by_product.get(product_name, [])
        new_name = snap(m.feature_name, names)
        if new_name != m.feature_name:
            print(f"  {product_name} | '{m.feature_name}'  ->  '{new_name}'")
            changed_pairs.add((product_name, m.feature_name))
            changed_pairs.add((product_name, new_name))
            if apply:
                m.feature_name = new_name
            updates += 1

    print(f"\nmention rows to update: {updates}")
    print(f"feature buckets touched (old+new): {len(changed_pairs)}")

    if apply:
        session.commit()

        # wipe stale clusters for every touched (product, feature) pair —
        # clustering_scoring.py rebuilds them from the corrected mentions
        deleted_clusters = 0
        for product_name, feature_name in changed_pairs:
            old_cluster_ids = [
                c.id for c in session.query(IssueCluster.id)
                .filter_by(product_name=product_name, feature_name=feature_name)
            ]
            if old_cluster_ids:
                session.query(IssueClusterMember).filter(
                    IssueClusterMember.issue_cluster_id.in_(old_cluster_ids)
                ).delete(synchronize_session=False)
                session.query(IssueCluster).filter_by(
                    product_name=product_name, feature_name=feature_name
                ).delete()
                deleted_clusters += len(old_cluster_ids)
        session.commit()
        print(f"stale clusters deleted: {deleted_clusters}")
        print("\ndone. run clustering_scoring stage next to rebuild.")
    else:
        print("\ndry run only — no changes committed. re-run with --apply to commit.")

    session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(apply=args.apply)