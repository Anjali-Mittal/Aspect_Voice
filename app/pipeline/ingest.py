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


def run_ingestion():
    cfg = get_config()
    Session = get_session_factory(cfg["storage"]["db_url"])
    session = Session()

    # source_ids already committed in earlier runs — loaded once, up front,
    # so every dedup check below is an in-memory lookup, not a DB round trip
    known_ids = {row.source_id for row in session.query(RawFeedback.source_id)}

    inserted = 0
    for target in cfg["targets"]:
        for source_name, fetch_fn in SOURCE_FETCHERS.items():
            if not cfg["sources"].get(source_name, {}).get("enabled"):
                continue
            for item in fetch_fn(target):
                # catches both already-committed rows AND duplicates returned
                # within this same run (e.g. one video/comment surfacing under
                # two different search terms)
                if item["source_id"] in known_ids:
                    continue
                known_ids.add(item["source_id"])
                session.add(RawFeedback(**item))
                inserted += 1
            session.commit()

    session.close()
    return {"inserted": inserted}