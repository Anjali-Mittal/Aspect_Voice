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

    inserted = 0
    for target in cfg["targets"]:
        for source_name, fetch_fn in SOURCE_FETCHERS.items():
            if not cfg["sources"].get(source_name, {}).get("enabled"):
                continue
            for item in fetch_fn(target):
                exists = session.query(RawFeedback).filter_by(source_id=item["source_id"]).first()
                if exists:
                    continue
                session.add(RawFeedback(**item))
                inserted += 1
            session.commit()

    session.close()
    return {"inserted": inserted}