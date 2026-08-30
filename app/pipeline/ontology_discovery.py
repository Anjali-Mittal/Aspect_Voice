import random
from collections import defaultdict
from app.config import get_config
from app.models.db import CleanFeedback, FeatureOntology, get_session_factory
from app.llm.client import call_llm_json

DISCOVERY_PROMPT = """Product: {product_name}
Below are real customer feedback snippets about this product.
Read them and discover the distinct FEATURES or ASPECTS people talk about
(e.g. for a vehicle this might be things like braking, mileage, seat comfort,
switch quality, headlight throw, service experience -- but do NOT assume any
of these, derive the actual list purely from the text below).

Return JSON: {{"features": [{{"name": "...", "description": "..."}}, ...]}}
Keep names short (2-4 words), merge near-duplicates, aim for 10-25 features.

Feedback:
{snippets}
"""

MERGE_PROMPT = """Below are candidate product features/aspects discovered from
several separate batches of customer feedback about the same product. The
same real feature often appears multiple times with slightly different
names (e.g. "brakes", "braking system", "brake feel" are one feature).

Merge these into one final deduplicated list. Keep names short (2-4 words),
keep the clearest/most representative description for each, aim for the
smallest list that doesn't lose any genuinely distinct feature.

Return JSON: {{"features": [{{"name": "...", "description": "..."}}, ...]}}

Candidates:
{candidates}
"""


def _discover_from_batch(batch, product_name: str) -> list[dict]:
    snippets = "\n".join(f"- {item.clean_text[:400]}" for item in batch)
    prompt = DISCOVERY_PROMPT.format(product_name=product_name, snippets=snippets)
    result = call_llm_json(prompt)
    return result.get("features", [])


def run_ontology_discovery():
    cfg = get_config()
    Session = get_session_factory(cfg["storage"]["db_url"])
    session = Session()
    sample_size = cfg["pipeline"]["ontology_discovery_sample_size"]
    batch_size = cfg["pipeline"]["ontology_discovery_batch_size"]

    clean = session.query(CleanFeedback).filter(CleanFeedback.is_duplicate_of.is_(None)).all()
    if not clean:
        session.close()
        return {"features": 0, "note": "no clean feedback yet, run ingestion + relevance_filter + cleaning first"}

    by_product = defaultdict(list)
    for item in clean:
        by_product[item.product_name].append(item)

    results = {}
    for product_name, rows in by_product.items():
        sample = random.sample(rows, min(sample_size, len(rows)))

        # Chunk into batches so no single LLM call ever gets an unbounded prompt —
        # a 300-item sample in one call would be ~30k tokens; capped at batch_size
        # per call instead (default 50 -> ~5k tokens).
        batches = [sample[i:i + batch_size] for i in range(0, len(sample), batch_size)]

        candidates: list[dict] = []
        for batch in batches:
            candidates.extend(_discover_from_batch(batch, product_name))

        if len(batches) > 1:
            # merge/dedupe across batches — this call only sees short names +
            # descriptions, never the original feedback text, so it stays cheap
            # even with hundreds of candidates
            candidate_lines = "\n".join(f"- {c['name']}: {c.get('description', '')}" for c in candidates)
            merge_result = call_llm_json(MERGE_PROMPT.format(candidates=candidate_lines))
            final_features = merge_result.get("features", [])
        else:
            final_features = candidates

        # replace existing ontology for this product (rediscovery overwrites)
        session.query(FeatureOntology).filter_by(product_name=product_name).delete()
        for f in final_features:
            session.add(FeatureOntology(
                product_name=product_name,
                feature_name=f["name"],
                description=f.get("description", ""),
            ))
        session.commit()
        results[product_name] = {"features": len(final_features), "batches_processed": len(batches)}

    session.close()
    return {"per_product": results}