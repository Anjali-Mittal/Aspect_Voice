"""Reddit ingestion via PRAW. Free tier, app-only auth, no credit card.
Create app at https://www.reddit.com/prefs/apps -> type 'script'.

Reddit's app-approval queue can take up to a week for a new script app to
start working. Rather than crash the whole pipeline while waiting, this
skips Reddit cleanly if credentials aren't set yet — ingest still runs
normally for whatever sources ARE configured.
"""
import os
from datetime import datetime
from app.config import get_config


def fetch_reddit_feedback(target: dict):
    cfg = get_config()
    rcfg = cfg["sources"]["reddit"]
    if not rcfg["enabled"]:
        return []

    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = os.getenv("REDDIT_USER_AGENT")

    if not client_id or not client_secret:
        print("[ingest] Reddit: REDDIT_CLIENT_ID/SECRET not set yet — skipping "
              "(this is normal while a new Reddit app is pending approval, "
              "which can take up to a week). Other sources still run.")
        return []

    import praw

    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent or "customer-voice-intelligence/0.1",
    )

    items = []
    product_name = target["product_name"]

    for subreddit_name in rcfg["subreddits"]:
        subreddit = reddit.subreddit(subreddit_name)
        for term in rcfg["search_terms"]:
            term = term.format(product_name=product_name)
            for submission in subreddit.search(term, limit=rcfg["post_limit"]):
                items.append({
                    "source": "reddit",
                    "source_id": f"post_{submission.id}",
                    "product_name": product_name,
                    "text": f"{submission.title}\n{submission.selftext}",
                    "author": str(submission.author),
                    "url": f"https://reddit.com{submission.permalink}",
                    "created_at": datetime.utcfromtimestamp(submission.created_utc),
                    "meta": {"score": submission.score, "subreddit": subreddit_name},
                })
                submission.comments.replace_more(limit=0)
                for comment in submission.comments.list()[: rcfg["comment_limit_per_post"]]:
                    items.append({
                        "source": "reddit",
                        "source_id": f"comment_{comment.id}",
                        "product_name": product_name,
                        "text": comment.body,
                        "author": str(comment.author),
                        "url": f"https://reddit.com{comment.permalink}",
                        "created_at": datetime.utcfromtimestamp(comment.created_utc),
                        "meta": {"score": comment.score, "subreddit": subreddit_name},
                    })
    return items