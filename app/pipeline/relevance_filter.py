from app.config import get_config
from app.models.db import RawFeedback, get_session_factory
from app.llm.client import call_llm_json
from collections import defaultdict

PROMPT_TEMPLATE = """Product: {product_name}
Below are {n} numbered feedback snippets scraped from the internet.
For each, decide:
- relevant: true if it is genuinely about this product (or its direct experience),
  false if off-topic, spam, unrelated small talk, or about a different product.
- substantive: true if it contains an actual opinion/experience/complaint/praise,
  false if it's just a greeting, emoji-only, or a question with no content.

Return JSON: {{"results": [{{"i": 0, "relevant": true, "substantive": true}}, ...]}}

Snippets:
{snippets}
"""


def run_relevance_filter():
    cfg = get_config()
    Session = get_session_factory(cfg["storage"]["db_url"])
    session = Session()
    batch_size = cfg["pipeline"]["relevance_filter_batch_size"]

    pending = session.query(RawFeedback).filter(RawFeedback.is_relevant.is_(None)).all()
    by_product = defaultdict(list)
    for item in pending:
        by_product[item.product_name].append(item)

    updated = 0
    for product_name, rows in by_product.items():
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            snippets = "\n".join(f"{j}. {item.text[:500]}" for j, item in enumerate(batch))
            prompt = PROMPT_TEMPLATE.format(
                product_name=product_name, n=len(batch), snippets=snippets
            )
            result = call_llm_json(prompt)
            for r in result.get("results", []):
                idx = r["i"]
                if idx >= len(batch):
                    continue
                batch[idx].is_relevant = 1 if (r.get("relevant") and r.get("substantive")) else 0
                updated += 1
            session.commit()

    session.close()
    return {"updated": updated}