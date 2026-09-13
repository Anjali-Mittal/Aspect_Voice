import time
from app.config import get_config
from app.models.db import CleanFeedback, FeatureOntology, AspectMention, get_session_factory
from app.llm.client import call_llm_json, LLMError
from collections import defaultdict

PROMPT_TEMPLATE = """Product: {product_name}
Known feature list (use ONLY these names, do not invent new ones):
{feature_list}

Below are {n} numbered feedback snippets. For each snippet, extract every
feature it actually discusses. A snippet can map to 0, 1, or multiple features.

For each match give:
- feature: name, must match list exactly
- sentiment: positive/negative/neutral
- severity (0.0-1.0, ONLY for negative sentiment, else 0): rate the real-world
  functional/business IMPACT of the problem, NOT how angry or emotional the
  wording is. A calm complaint about a dangerous defect is still high severity;
  an all-caps rant about a slow-loading screen is still low severity. Anchor to:
    0.0-0.3  cosmetic/minor annoyance, no real impact on using the product
             (typos, UI polish, load time, "looks cheap")
    0.3-0.6  a real inconvenience or missing feature, workaround exists,
             doesn't block core use
    0.6-0.85 blocks or seriously degrades core functionality (can't complete
              the product's main job), but not a safety/injury risk
    0.85-1.0 physical safety risk, injury/accident risk, or total product
              failure with no workaround
  Do not default to the middle or top of the range — most complaints are
  genuinely minor (0.0-0.4); reserve 0.85+ for true safety/failure cases.
- safety_related (true/false): true ONLY if the snippet describes an actual
  physical safety or accident/injury risk (e.g. vehicle cutting out while
  riding, brake failure, fire risk) — NOT general dissatisfaction, pricing,
  or app/software annoyances, even if described in strong language.
- snippet: short verbatim quote (<=20 words) as evidence

Return JSON:
{{"results": [{{"i": 0, "mentions": [{{"feature": "...", "sentiment": "...", "severity": 0.0, "safety_related": false, "snippet": "..."}}]}}, ...]}}

Snippets:
{snippets}
"""


def run_aspect_extraction():
    cfg = get_config()
    Session = get_session_factory(cfg["storage"]["db_url"])
    batch_size = cfg["pipeline"]["aspect_extraction_batch_size"]

    # Short-lived session for this one read, then closed immediately —
    # not held open for the run. Same reasoning as the per-batch write
    # sessions below: a connection idle for minutes across many slow LLM
    # calls is what Neon's serverless Postgres was killing mid-request.
    with Session() as session:
        pending = (
            session.query(CleanFeedback)
            .filter(CleanFeedback.is_duplicate_of.is_(None), CleanFeedback.aspect_extraction_done.is_(False))
            .all()
        )
    if not pending:
        return {"mentions_created": 0}

    by_product = defaultdict(list)
    for item in pending:
        by_product[item.product_name].append(item)

    created = 0
    skipped_products = {}
    failed_batches = []  # batches the LLM never returned usable JSON for, after retries — logged, not fatal
    for product_name, rows in by_product.items():
        with Session() as session:
            features = session.query(FeatureOntology).filter_by(product_name=product_name).all()
        if not features:
            skipped_products[product_name] = "no feature ontology yet, run ontology_discovery first"
            continue

        feature_list = "\n".join(f"- {f.feature_name}: {f.description}" for f in features)
        total_batches = (len(rows) + batch_size - 1) // batch_size

        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            batch_num = i // batch_size + 1
            print(f"[aspect-extraction] {product_name}: batch {batch_num}/{total_batches} (rows {i}-{i + len(batch) - 1})...", flush=True)
            snippets = "\n".join(f"{j}. {item.clean_text[:500]}" for j, item in enumerate(batch))
            prompt = PROMPT_TEMPLATE.format(
                product_name=product_name, feature_list=feature_list, n=len(batch), snippets=snippets
            )
            try:
                result = call_llm_json(prompt)
            except LLMError as e:
                print(f"[aspect-extraction] {product_name}: batch {batch_num}/{total_batches} FAILED — {str(e)[:150]}", flush=True)
                # one batch's LLM output was unrecoverably malformed — skip
                # just this batch (its reviews stay "pending" and get
                # retried on the next run) instead of failing the whole
                # extraction request and losing every batch after it
                failed_batches.append({"product": product_name, "batch_start": i, "error": str(e)[:300]})
                # a failure here is usually free-tier rate limiting (Groq/
                # Gemini RPM caps) rather than a bad response — firing the
                # next batch immediately just compounds it. Back off before
                # continuing; a clean batch doesn't pay this cost.
                time.sleep(5)
                continue
            try:
                batch_created = 0
                raw_results = result.get("results", [])
                raw_mention_count = sum(len(r.get("mentions", [])) for r in raw_results if isinstance(r, dict))
                new_mentions = []
                for r in raw_results:
                    if not isinstance(r, dict) or "i" not in r:
                        continue
                    idx = r["i"]
                    # Gemini sometimes emits numeric "i" as a float (0.0
                    # instead of 0) even when asked for an int — isinstance
                    # check alone silently dropped every single mention in
                    # that case. Accept int-valued floats too.
                    if isinstance(idx, float) and idx.is_integer():
                        idx = int(idx)
                    if not isinstance(idx, int) or idx >= len(batch):
                        continue
                    for m in r.get("mentions", []):
                        if not isinstance(m, dict):
                            continue
                        feature = (m.get("feature") or "").strip()
                        if not feature:
                            continue  # LLM returned an empty feature — not a usable tag, skip
                        sentiment = (m.get("sentiment") or "neutral").strip().lower()
                        if sentiment not in ("positive", "negative", "neutral"):
                            sentiment = "neutral"
                        new_mentions.append(AspectMention(
                            clean_feedback_id=batch[idx].id,
                            feature_name=feature,
                            sentiment=sentiment,
                            severity=float(m.get("severity") or 0),
                            safety_related=bool(m.get("safety_related", False)),
                            snippet=(m.get("snippet") or "").strip(),
                        ))
                        batch_created += 1
                if batch_created == 0 and raw_mention_count == 0:
                    # Gemini returned a well-formed response with nothing
                    # in it — could be legitimately content-free reviews
                    # (short praise/emoji with no feature named), or the
                    # prompt/model quietly declining. Show what was
                    # actually sent so it's obvious which one this is.
                    sample = [item.clean_text[:120] for item in batch[:3]]
                    print(f"[aspect-extraction] {product_name}: batch {batch_num}/{total_batches} — 0 raw mentions. Sample reviews sent: {sample}", flush=True)
                if batch_created == 0 and raw_mention_count > 0:
                    # the LLM found mentions but every single one got
                    # filtered out downstream — a parsing mismatch, not a
                    # genuinely quiet batch. Surface it instead of silently
                    # reporting 0.
                    print(f"[aspect-extraction] {product_name}: batch {batch_num}/{total_batches} — LLM returned {raw_mention_count} raw mentions but 0 survived filtering. Sample: {raw_results[:1]}", flush=True)

                # Short-lived session for just this batch's write, opened
                # fresh right before use. The long LLM call above can take
                # many seconds; holding one DB connection open across the
                # entire multi-minute, many-batch run is what let Neon's
                # serverless Postgres drop it mid-write ("server closed the
                # connection unexpectedly"). pool_pre_ping only validates a
                # connection at checkout — it can't help a connection that
                # goes stale while already checked out and idle.
                batch_ids = [item.id for item in batch]
                write_session = Session()
                try:
                    write_session.add_all(new_mentions)
                    write_session.query(CleanFeedback).filter(CleanFeedback.id.in_(batch_ids)).update(
                        {"aspect_extraction_done": True}, synchronize_session=False
                    )
                    write_session.commit()
                    created += batch_created
                finally:
                    write_session.close()

                print(f"[aspect-extraction] {product_name}: batch {batch_num}/{total_batches} done, +{batch_created} mentions (raw: {raw_mention_count})", flush=True)
            except Exception as e:
                # malformed shape survived call_llm_json's own checks (e.g. a
                # field with an unexpected type), or the write itself failed
                # (e.g. a dropped connection) — skip this batch rather than
                # crash the whole run; its reviews stay pending for the next
                # call, since aspect_extraction_done is only set on success
                failed_batches.append({"product": product_name, "batch_start": i, "error": str(e)[:300]})
                continue

    return {"mentions_created": created, "skipped_products": skipped_products, "failed_batches": failed_batches}