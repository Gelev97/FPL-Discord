import requests
import os
import time
from datetime import datetime, timedelta, timezone

# ==== CONFIG ====
SUBREDDIT = "FantasyPL"
FLAIR = "News"
LIMIT = 50  # fetch more, filter later
DISCORD_WEBHOOK = os.get_env("DISCORD_FPL_NEWS_WEBHOOK")
REQUEST_TIMEOUT = 10  # seconds
MAX_RETRIES = 3
# ===============

def fetch_reddit_posts(subreddit, flair, limit=50):
    url = (
        f"https://www.reddit.com/r/{subreddit}/search.json"
        f"?q=flair_name%3A%22{flair}%22&restrict_sr=on&sort=new&limit={limit}"
    )
    headers = {"User-Agent": "github-action-script/0.1"}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            return r.json()["data"]["children"]
        except Exception as e:
            print(f"[Attempt {attempt}] Failed to fetch posts: {e}")
            if attempt == MAX_RETRIES:
                raise
            time.sleep(2 * attempt)  # exponential backoff

def send_to_discord(webhook, content):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.post(webhook, json={"content": content}, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            return
        except Exception as e:
            print(f"[Attempt {attempt}] Failed to send to Discord: {e}")
            if attempt == MAX_RETRIES:
                raise
            time.sleep(2 * attempt)

def main():
    if not DISCORD_WEBHOOK:
        raise ValueError("Please set DISCORD_WEBHOOK as an environment variable")

    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)

    # Daily window: yesterday 18:00 UTC → today 18:00 UTC
    start_time = yesterday.replace(hour=18, minute=0, second=0, microsecond=0)
    end_time   = now.replace(hour=18, minute=0, second=0, microsecond=0)

    start_ts = start_time.timestamp()
    end_ts = end_time.timestamp()

    print(f"Fetching posts between {start_time} and {end_time}")

    posts = fetch_reddit_posts(SUBREDDIT, FLAIR, LIMIT)
    for post in posts:
        data = post["data"]
        created = data["created_utc"]

        if start_ts <= created < end_ts:
            title = data["title"]
            url = f"https://reddit.com{data['permalink']}"
            message = f"📰 **{title}**\n{url}"
            print("Sending:", message)
            send_to_discord(DISCORD_WEBHOOK, message)

if __name__ == "__main__":
    main()
