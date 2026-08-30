"""YouTube transcript ingestion. Reuses the same video search as
youtube_source.py (search_terms in config), but pulls the full caption
transcript per video instead of comments, then chunks it — a raw
transcript is one long blob covering many topics, useless to aspect
extraction as a single row; chunking gives each segment its own
RawFeedback row like a comment does.

youtube-transcript-api is unofficial (scrapes caption tracks) — free,
no API key, no quota, but no SLA. Videos with no captions (auto or
manual) are skipped, not retried.
"""
from datetime import datetime
from app.config import get_config, get_secret


def _chunk_transcript(segments, chunk_words: int):
    """Group timestamped caption segments into ~chunk_words-word blocks,
    keeping the start timestamp of each chunk for a deep link."""
    chunks = []
    current_words, current_start, word_count = [], None, 0
    for seg in segments:
        if current_start is None:
            current_start = seg["start"]
        current_words.append(seg["text"])
        word_count += len(seg["text"].split())
        if word_count >= chunk_words:
            chunks.append((current_start, " ".join(current_words)))
            current_words, current_start, word_count = [], None, 0
    if current_words:
        chunks.append((current_start, " ".join(current_words)))
    return chunks


def fetch_youtube_transcript_feedback(target: dict):
    from googleapiclient.discovery import build
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound

    cfg = get_config()
    ycfg = cfg["sources"]["youtube"]
    tcfg = cfg["sources"]["youtube_transcripts"]
    if not ycfg["enabled"] or not tcfg["enabled"]:
        return []

    chunk_words = tcfg.get("chunk_words", 150)
    max_videos = tcfg.get("max_videos", ycfg["max_videos"])

    youtube = build("youtube", "v3", developerKey=get_secret("YOUTUBE_API_KEY"))
    product_name = target["product_name"]
    ytt = YouTubeTranscriptApi()
    items = []

    for term in ycfg["search_terms"]:
        term = term.format(product_name=product_name)
        search_resp = youtube.search().list(
            q=term, part="id,snippet", type="video", maxResults=max_videos
        ).execute()

        for video in search_resp.get("items", []):
            video_id = video["id"]["videoId"]
            video_title = video["snippet"]["title"]
            try:
                transcript = ytt.fetch(video_id)
            except (TranscriptsDisabled, NoTranscriptFound):
                continue
            except Exception:
                continue  # any other transcript-fetch failure — skip this video, don't fail the run

            segments = [{"text": s.text, "start": s.start} for s in transcript]
            for start_sec, chunk_text in _chunk_transcript(segments, chunk_words):
                items.append({
                    "source": "youtube_transcript",
                    "source_id": f"{video_id}_t{int(start_sec)}",
                    "product_name": product_name,
                    "text": chunk_text,
                    "author": None,
                    "url": f"https://youtube.com/watch?v={video_id}&t={int(start_sec)}s",
                    "created_at": None,  # transcript has no publish date of its own; video's is on the comment rows already
                    "meta": {"video_title": video_title, "video_id": video_id},
                })
    return items