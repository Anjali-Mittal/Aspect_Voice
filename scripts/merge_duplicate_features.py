"""
One-time (or occasional re-run) fix: merges near-duplicate FeatureOntology
entries themselves — not just mention-level drift. Fixes cases like
"Vehicle Styling" / "Vehicle Design and Styling" or "Price & Value" /
"Pricing and Value" that rapidfuzz (word-order/length-sensitive) misses
but are obviously the same real feature semantically. Uses the same Groq
LLM already in your pipeline (free tier, no new dependency).

Run this BEFORE scripts/backfill_fix_feature_names.py, since that script
snaps mentions to whatever's currently in FeatureOntology — if the
ontology itself still has duplicates, backfill has nothing correct to
snap to.

Usage:
    python -m scripts.merge_duplicate_features --dry-run
    python -m scripts.merge_duplicate_features --apply
"""

import argparse
import re
from collections import defaultdict

from app.config import get_config
from app.llm.client import call_llm_json, LLMError
from app.models.db import (
    FeatureOntology, AspectMention, CleanFeedback, IssueCluster, IssueClusterMember,
    get_session_factory,
)

MERGE_PROMPT = """Below is the full list of discovered features/aspects for
a product. Some entries are the SAME real feature described with different
wording. Merge aggressively on MEANING, not exact wording — these are all
single merges:
  "Vehicle Styling" + "Vehicle Design and Styling" -> one feature
  "Price & Value" + "Pricing and Value" -> one feature
  "Vehicle Reliability" + "Safety and Reliability" (general breakdowns vs.
    vehicle unexpectedly stopping/turning off — both ARE reliability) -> one feature
  "Engine Start" + "Starting Issues" -> one feature
Only keep separate what a customer would clearly describe as a DIFFERENT
part of the product (e.g. "Battery Range" vs "Battery Charging Speed" are
different enough to stay separate).

Group every entry below into clusters. For each cluster's "canonical" name:
- If picking one of the original member names, copy it EXACTLY.
- If writing a new name instead, it MUST be 1-3 words, a plain feature/
  category label — never a sentence, never a description, never punctuation
  like colons or periods. ("Charging System: Reliability, errors, and
  overall charging process." is WRONG — write "Charging System" instead.)

List every original entry that belongs to each cluster, INCLUDING entries
with no duplicate (a cluster of 1 is fine and expected for most entries).
Every original entry must appear in exactly one cluster's "members" list,
spelled EXACTLY as given below.

Return JSON:
{{"groups": [{{"canonical": "...", "members": ["...", "..."]}}, ...]}}

Entries:
{entries}
"""


def main(apply: bool):
    cfg = get_config()
    Session = get_session_factory(cfg["storage"]["db_url"])
    session = Session()

    all_features = session.query(FeatureOntology).all()
    by_product = defaultdict(list)
    for f in all_features:
        by_product[f.product_name].append(f)

    total_merged_groups = 0

    for product_name, rows in by_product.items():
        if len(rows) < 2:
            continue

        entries_text = "\n".join(f"- {r.feature_name}: {r.description or ''}" for r in rows)
        prompt = MERGE_PROMPT.format(entries=entries_text)

        try:
            result = call_llm_json(prompt)
        except LLMError as e:
            print(f"[{product_name}] LLM call failed, skipping: {e}")
            continue

        groups = result.get("groups", [])
        by_name = {r.feature_name: r for r in rows}
        norm_lookup = {n.strip().casefold(): n for n in by_name}  # tolerate LLM
        # respelling members with different case/whitespace/trailing punctuation
        seen_names = set()

        print(f"\n[{product_name}] — {len(rows)} features -> {len(groups)} groups")

        for g in groups:
            canonical = (g.get("canonical") or "").strip()
            raw_members = g.get("members", [])
            members = [norm_lookup[m.strip().casefold()] for m in raw_members if m.strip().casefold() in norm_lookup]
            if not canonical or not members:
                continue
            seen_names.update(members)

            # Guardrail: reject any canonical that isn't a short label —
            # the LLM occasionally echoes a description/sentence instead
            # of a name (observed: "Charging System: Reliability, errors,
            # and overall charging process."). Prefer the shortest member
            # name; if there's only one member and IT is the bad long
            # text (a pre-existing bad FeatureOntology row), truncate at
            # the first punctuation mark and cap word count instead.
            if len(canonical.split()) > 4 or any(ch in canonical for ch in ":.;"):
                if len(members) > 1:
                    canonical = min(members, key=len)
                else:
                    head = re.split(r"[:.;]", canonical)[0].strip()
                    canonical = " ".join(head.split()[:4])

            if len(members) == 1 and members[0] == canonical:
                continue  # no-op, nothing to merge

            print(f"  merge {members}  ->  '{canonical}'")
            total_merged_groups += 1

            if not apply:
                continue

            member_rows = [by_name[m] for m in members]
            # keep the description from whichever member has the longest one
            best_description = max((r.description or "" for r in member_rows), key=len)

            # delete all member ontology rows, insert one canonical row
            for r in member_rows:
                session.delete(r)
            session.add(FeatureOntology(
                product_name=product_name,
                feature_name=canonical,
                description=best_description,
            ))

            # remap mentions
            session.query(AspectMention).filter(
                AspectMention.feature_name.in_(members),
                AspectMention.clean_feedback_id.in_(
                    session.query(CleanFeedback.id).filter(CleanFeedback.product_name == product_name)
                ),
            ).update({AspectMention.feature_name: canonical}, synchronize_session=False)

            # wipe stale clusters for every old name AND the canonical name
            # (canonical may already have its own clusters that now need
            # to absorb the merged mentions on next clustering run)
            touched_names = set(members) | {canonical}
            old_cluster_ids = [
                c.id for c in session.query(IssueCluster.id)
                .filter(IssueCluster.product_name == product_name, IssueCluster.feature_name.in_(touched_names))
            ]
            if old_cluster_ids:
                session.query(IssueClusterMember).filter(
                    IssueClusterMember.issue_cluster_id.in_(old_cluster_ids)
                ).delete(synchronize_session=False)
                session.query(IssueCluster).filter(
                    IssueCluster.product_name == product_name, IssueCluster.feature_name.in_(touched_names)
                ).delete(synchronize_session=False)

        missed = set(by_name.keys()) - seen_names
        if missed:
            print(f"  [warn] LLM omitted from groups, left untouched: {missed}")

        if apply:
            session.commit()

    print(f"\ntotal merge groups: {total_merged_groups}")
    if not apply:
        print("dry run only — no changes committed. re-run with --apply to commit.")
    else:
        print("done. run backfill_fix_feature_names.py next (catches any remaining "
              "mention-level drift), then rerun clustering + scoring.")

    session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(apply=args.apply)