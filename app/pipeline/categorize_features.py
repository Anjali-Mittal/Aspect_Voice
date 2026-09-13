"""One-off categorization pass over the feature ontology — not a re-run of
ontology discovery itself. Groups already-discovered features (e.g. "Engine
Stalling", "ABS System", "Braking System") into a small set of categories
(e.g. "Engine & Powertrain", "Braking & Safety") for the sidebar's
collapsible grouping in Product Insights.

Cheap and fast: one LLM call per product, over just the feature
name+description list (10-40 short lines), never the underlying review
text. Idempotent — only categorizes features that don't have one yet, so
re-running after ontology discovery adds new features doesn't force
re-categorizing everything.
"""
from collections import defaultdict
from app.config import get_config
from app.models.db import FeatureOntology, get_session_factory
from app.llm.client import call_llm_json

CATEGORIZE_PROMPT = """Product: {product_name}
Below is a list of features/aspects already discovered for this product,
each with an id and a short description.

Group them into a small number of clear categories (aim for 4-8 categories
total — fewer if the list is short). Every feature must be assigned to
exactly one category. Category names should be short (2-4 words, e.g.
"Engine & Powertrain", "Braking & Safety", "Comfort & Ergonomics",
"Electrical & Battery", "Build & Pricing") and make sense for a vehicle
product, but derive them from what's actually in the list below — don't
force-fit an irrelevant category.

Features:
{feature_lines}

Return JSON: {{"assignments": [{{"id": 0, "category": "..."}}, ...]}}
One entry per feature id above, every id must appear exactly once.
"""


def run_categorize_features():
    cfg = get_config()
    Session = get_session_factory(cfg["storage"]["db_url"])

    with Session() as session:
        uncategorized = (
            session.query(FeatureOntology)
            .filter(FeatureOntology.category.is_(None))
            .all()
        )
        by_product = defaultdict(list)
        for f in uncategorized:
            by_product[f.product_name].append((f.id, f.feature_name, f.description or ""))

    if not by_product:
        return {"categorized": 0, "note": "every feature already has a category"}

    results = {}
    for product_name, features in by_product.items():
        # local index (0..n-1) for the prompt, not the real DB id — keeps
        # the prompt short and the LLM's job simple; mapped back below
        feature_lines = "\n".join(f"{i}. {name}: {desc}" for i, (_, name, desc) in enumerate(features))
        prompt = CATEGORIZE_PROMPT.format(product_name=product_name, feature_lines=feature_lines)
        try:
            result = call_llm_json(prompt)
        except Exception as e:
            results[product_name] = {"error": str(e)[:300]}
            continue

        category_by_index = {}
        for a in result.get("assignments", []):
            if not isinstance(a, dict):
                continue
            idx = a.get("id")
            category = (a.get("category") or "").strip()
            if isinstance(idx, int) and 0 <= idx < len(features) and category:
                category_by_index[idx] = category

        with Session() as write_session:
            updated = 0
            for i, (feature_id, _, _) in enumerate(features):
                category = category_by_index.get(i, "Other")  # LLM skipped it — don't leave it uncategorized forever
                write_session.query(FeatureOntology).filter_by(id=feature_id).update({"category": category})
                updated += 1
            write_session.commit()
        results[product_name] = {"categorized": updated}

    return {"per_product": results}