"""Stage between relevance-filter and ontology-discovery. Two jobs:

1. Normalize text (strip whitespace/control chars, collapse repeats) so
   downstream LLM prompts see clean input.
2. Fuzzy-dedup: exact-ID dedup already happened at ingest, but the same
   review often gets cross-posted or lightly reworded across sources/pages.
   rapidfuzz catches near-duplicates that source_id-based dedup can't.

Reads only RawFeedback rows already marked relevant by relevance_filter.
Writes CleanFeedback — everything downstream reads from that table, never
from RawFeedback directly.
"""
import re
from rapidfuzz import fuzz
from app.config import get_config
from app.models.db import RawFeedback, CleanFeedback, get_session_factory

FUZZY_DUPLICATE_THRESHOLD = 92  # rapidfuzz ratio 0-100; >= this = treat as duplicate


def _normalize(text: str) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)   # strip control chars
    text = re.sub(r"\s+", " ", text)                           # collapse whitespace
    text = re.sub(r"(.)\1{4,}", r"\1\1\1", text)                # "sooooo" -> "sooo"
    return text.strip()


def _dedup_key(text: str) -> str:
    """Case/punctuation-insensitive form used only for the fuzzy-match
    comparison, so the same comment re-cased or re-punctuated across
    sources still matches (e.g. a cross-post with a trailing '.' added,
    or a source that lowercases everything)."""
    return re.sub(r"[^\w\s]", "", text.lower())


def run_cleaning(product_name: str | None = None):
    cfg = get_config()
    Session = get_session_factory(cfg["storage"]["db_url"])
    session = Session()

    already_cleaned_raw_ids = {c.raw_feedback_id for c in session.query(CleanFeedback.raw_feedback_id)}
    raw_query = session.query(RawFeedback).filter(RawFeedback.is_relevant == 1)
    if product_name:
        raw_query = raw_query.filter(RawFeedback.product_name == product_name)
    pending = [r for r in raw_query.all() if r.id not in already_cleaned_raw_ids]

    # existing clean texts (per product), for fuzzy comparison against new items
    existing_by_product = {}
    for c in session.query(CleanFeedback).all():
        existing_by_product.setdefault(c.product_name, []).append(c)

    created, duplicates = 0, 0
    print(f"[cleaning] {len(pending)} pending rows to check...", flush=True)

    for idx, raw in enumerate(pending, start=1):
        if idx % 100 == 0:
            print(f"[cleaning] ...{idx}/{len(pending)} checked (+{created} clean, +{duplicates} dupes so far)", flush=True)
        clean_text = _normalize(raw.text)
        if len(clean_text) < 10:  # too short to be a real opinion, drop silently
            continue

        product_pool = existing_by_product.setdefault(raw.product_name, [])
        dup_of = None
        key = _dedup_key(clean_text)
        for existing in product_pool:
            if fuzz.ratio(key, _dedup_key(existing.clean_text)) >= FUZZY_DUPLICATE_THRESHOLD:
                dup_of = existing
                break

        row = CleanFeedback(
            raw_feedback_id=raw.id,
            product_name=raw.product_name,
            clean_text=clean_text,
            created_at=raw.created_at,
            is_duplicate_of=dup_of.id if dup_of else None,
        )
        session.add(row)
        session.flush()  # get row.id before it's needed as a dup-target for the next item
        product_pool.append(row)

        if dup_of:
            duplicates += 1
        else:
            created += 1

    session.commit()
    session.close()
    print(f"[cleaning] done — {created} clean, {duplicates} duplicates", flush=True)
    return {"clean_created": created, "duplicates_marked": duplicates}