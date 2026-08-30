from app.config import get_config
from app.models.db import CleanFeedback, FeatureOntology, AspectMention, get_session_factory
from app.llm.client import call_llm_json
from collections import defaultdict

PROMPT_TEMPLATE = """Product: {product_name}
Known feature list (use ONLY these names, do not invent new ones):
{feature_list}

Below are {n} numbered feedback snippets. For each snippet, extract every
feature it actually discusses. A snippet can map to 0, 1, or multiple features.
For each match give: feature name (must match list exactly), sentiment
(positive/negative/neutral), severity (0.0-1.0, how strong/serious the
opinion is -- only meaningful for negative sentiment, else 0), and a short
verbatim snippet (<=20 words) as evidence.

Return JSON:
{{"results": [{{"i": 0, "mentions": [{{"feature": "...", "sentiment": "...", "severity": 0.0, "snippet": "..."}}]}}, ...]}}

Snippets:
{snippets}
"""


def run_aspect_extraction():
    cfg = get_config()
    Session = get_session_factory(cfg["storage"]["db_url"])
    session = Session()
    batch_size = cfg["pipeline"]["aspect_extraction_batch_size"]

    already_extracted_ids = {m.clean_feedback_id for m in session.query(AspectMention.clean_feedback_id)}
    pending = [
        item for item in session.query(CleanFeedback).filter(CleanFeedback.is_duplicate_of.is_(None)).all()
        if item.id not in already_extracted_ids
    ]
    if not pending:
        session.close()
        return {"mentions_created": 0}

    by_product = defaultdict(list)
    for item in pending:
        by_product[item.product_name].append(item)

    created = 0
    skipped_products = {}
    for product_name, rows in by_product.items():
        features = session.query(FeatureOntology).filter_by(product_name=product_name).all()
        if not features:
            skipped_products[product_name] = "no feature ontology yet, run ontology_discovery first"
            continue

        feature_list = "\n".join(f"- {f.feature_name}: {f.description}" for f in features)

        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            snippets = "\n".join(f"{j}. {item.clean_text[:500]}" for j, item in enumerate(batch))
            prompt = PROMPT_TEMPLATE.format(
                product_name=product_name, feature_list=feature_list, n=len(batch), snippets=snippets
            )
            result = call_llm_json(prompt)
            for r in result.get("results", []):
                idx = r["i"]
                if idx >= len(batch):
                    continue
                for m in r.get("mentions", []):
                    if not isinstance(m, dict) or "feature" not in m:
                        continue
                    session.add(AspectMention(
                        clean_feedback_id=batch[idx].id,
                        feature_name=m["feature"],
                        sentiment=m.get("sentiment", "neutral"),
                        severity=float(m.get("severity", 0)),
                        snippet=m.get("snippet", ""),
                    ))
                    created += 1
            session.commit()

    session.close()
    return {"mentions_created": created, "skipped_products": skipped_products}