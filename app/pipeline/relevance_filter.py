from app.config import get_config
from app.models.db import RawFeedback, get_session_factory
from app.llm.client import call_llm_json
from collections import defaultdict
from sqlalchemy.exc import OperationalError

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


def run_relevance_filter(product_name: str | None = None):
    cfg = get_config()
    Session = get_session_factory(cfg["storage"]["db_url"])
    batch_size = cfg["pipeline"]["relevance_filter_batch_size"]

    session = Session()
    query = session.query(RawFeedback).filter(RawFeedback.is_relevant.is_(None))
    if product_name:
        query = query.filter(RawFeedback.product_name == product_name)
    # Pull just the IDs — each batch below opens its own short-lived
    # session, so we don't want ORM objects bound to this one.
    pending = [(row.id, row.product_name, row.text) for row in query.all()]
    session.close()

    by_product = defaultdict(list)
    for row_id, prod, text in pending:
        by_product[prod].append((row_id, text))

    updated = 0
    for product_name, rows in by_product.items():
        total_batches = (len(rows) + batch_size - 1) // batch_size
        print(f"[relevance-filter] {product_name}: {len(rows)} rows -> {total_batches} batches", flush=True)
        for batch_num, i in enumerate(range(0, len(rows), batch_size), start=1):
            batch = rows[i:i + batch_size]
            snippets = "\n".join(f"{j}. {text[:500]}" for j, (_, text) in enumerate(batch))
            prompt = PROMPT_TEMPLATE.format(
                product_name=product_name, n=len(batch), snippets=snippets
            )
            print(f"[relevance-filter] {product_name}: batch {batch_num}/{total_batches}...", flush=True)
            # LLM call happens before any DB connection is opened for this
            # batch, so a slow call can never leave a Neon connection
            # idling long enough to be dropped mid-transaction.
            result = call_llm_json(prompt)

            decisions = {}
            for r in result.get("results", []):
                idx = r["i"]
                if idx >= len(batch):
                    continue
                row_id = batch[idx][0]
                decisions[row_id] = 1 if (r.get("relevant") and r.get("substantive")) else 0

            # Fresh session per batch: a brand-new connection is checked
            # out (and pre_ping-validated) right before this short commit,
            # so a connection dropped during the LLM call above never
            # surfaces here — retried once on a transient drop regardless.
            for attempt in (1, 2):
                batch_session = Session()
                try:
                    for row_id, is_relevant in decisions.items():
                        batch_session.query(RawFeedback).filter_by(id=row_id).update(
                            {"is_relevant": is_relevant}
                        )
                    batch_session.commit()
                    updated += len(decisions)
                    break
                except OperationalError:
                    batch_session.rollback()
                    if attempt == 2:
                        raise
                    print(f"[relevance-filter] {product_name}: batch {batch_num} DB hiccup, retrying...", flush=True)
                finally:
                    batch_session.close()
            print(f"[relevance-filter] {product_name}: batch {batch_num}/{total_batches} done", flush=True)

    return {"updated": updated}