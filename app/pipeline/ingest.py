from app.config import get_config
from app.models.db import RawFeedback, get_session_factory
from app.ingestion.reddit_source import fetch_reddit_feedback
from app.ingestion.youtube_source import fetch_youtube_feedback
from app.ingestion.youtube_transcript_source import fetch_youtube_transcript_feedback
from app.ingestion.review_site_source import fetch_review_site_feedback

SOURCE_FETCHERS = {
    "reddit": fetch_reddit_feedback,
    "youtube": fetch_youtube_feedback,
    "youtube_transcripts": fetch_youtube_transcript_feedback,
    "review_sites": fetch_review_site_feedback,
}


def run_ingestion(product_name: str | None = None):
    cfg = get_config()
    Session = get_session_factory(cfg["storage"]["db_url"])

    targets = cfg["targets"]
    if product_name:
        targets = [t for t in targets if t["product_name"] == product_name]

    # source_ids already committed in earlier runs — loaded once, up front,
    # in a short-lived session, so every dedup check below is an in-memory
    # lookup, not a DB round trip.
    with Session() as session:
        known_ids = {row.source_id for row in session.query(RawFeedback.source_id)}

    inserted = 0
    for target in targets:
        for source_name, fetch_fn in SOURCE_FETCHERS.items():
            if not cfg["sources"].get(source_name, {}).get("enabled"):
                continue
            # Fetch fully into memory first — this is the slow part (network
            # calls, and scraping's delay_seconds sleeps), with no DB
            # connection held open while it runs. Holding one here risks
            # Neon dropping it mid-fetch, same issue fixed in
            # relevance_filter.py/ontology_discovery.py.
            new_items = []
            for item in fetch_fn(target):
                # catches both already-committed rows AND duplicates returned
                # within this same run (e.g. one video/comment surfacing under
                # two different search terms)
                if item["source_id"] in known_ids:
                    continue
                known_ids.add(item["source_id"])
                new_items.append(item)

            if new_items:
                with Session() as write_session:
                    for item in new_items:
                        write_session.add(RawFeedback(**item))
                    write_session.commit()
                inserted += len(new_items)

    return {"inserted": inserted}