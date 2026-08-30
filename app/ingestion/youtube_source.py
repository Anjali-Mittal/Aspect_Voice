"""YouTube ingestion via YouTube Data API v3. Free quota (10k units/day),
key from https://console.cloud.google.com (no billing needed for this API's free quota).
"""
from datetime import datetime
from app.config import get_config, get_secret


def fetch_youtube_feedback():
    from googleapiclient.discovery import build

    cfg = get_config()
    ycfg = cfg["sources"]["youtube"]
    if not ycfg["enabled"]:
        return []

    youtube = build("youtube", "v3", developerKey=get_secret("YOUTUBE_API_KEY"))
    product_name = cfg["target"]["product_name"]
    items = []

    for term in ycfg["search_terms"]:
        search_resp = youtube.search().list(
            q=term, part="id,snippet", type="video", maxResults=ycfg["max_videos"]
        ).execute()

        for video in search_resp.get("items", []):
            video_id = video["id"]["videoId"]
            try:
                comments_resp = youtube.commentThreads().list(
                    videoId=video_id, part="snippet",
                    maxResults=min(ycfg["max_comments_per_video"], 100),
                    textFormat="plainText",
                ).execute()
            except Exception:
                continue  # comments disabled on this video

            for c in comments_resp.get("items", []):
                top = c["snippet"]["topLevelComment"]["snippet"]
                items.append({
                    "source": "youtube",
                    "source_id": c["id"],
                    "product_name": product_name,
                    "text": top["textDisplay"],
                    "author": top.get("authorDisplayName"),
                    "url": f"https://youtube.com/watch?v={video_id}&lc={c['id']}",
                    "created_at": datetime.fromisoformat(top["publishedAt"].replace("Z", "+00:00")),
                    "meta": {"likes": top.get("likeCount"), "video_title": video["snippet"]["title"]},
                })
    return items
