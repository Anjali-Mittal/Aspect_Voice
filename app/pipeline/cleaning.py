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


def run_cleaning():
    cfg = get_config()
    Session = get_session_factory(cfg["storage"]["db_url"])
    session = Session()

    already_cleaned_raw_ids = {c.raw_feedback_id for c in session.query(CleanFeedback.raw_feedback_id)}
    pending = [
        r for r in session.query(RawFeedback).filter(RawFeedback.is_relevant == 1).all()
        if r.id not in already_cleaned_raw_ids
    ]

    # existing clean texts (per product), for fuzzy comparison against new items
    existing_by_product = {}
    for c in session.query(CleanFeedback).all():
        existing_by_product.setdefault(c.product_name, []).append(c)

    created, duplicates = 0, 0

    for raw in pending:
        clean_text = _normalize(raw.text)
        if len(clean_text) < 10:  # too short to be a real opinion, drop silently
            continue

        product_pool = existing_by_product.setdefault(raw.product_name, [])
        dup_of = None
        for existing in product_pool:
            if fuzz.ratio(clean_text, existing.clean_text) >= FUZZY_DUPLICATE_THRESHOLD:
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
    return {"clean_created": created, "duplicates_marked": duplicates}
