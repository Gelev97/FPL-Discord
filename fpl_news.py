import os
import time
import praw
import requests
from datetime import datetime, timedelta, timezone

# Reddit setup
reddit = praw.Reddit(
    client_id=os.getenv("REDDIT_CLIENT_ID"),
    client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
    user_agent=os.getenv("REDDIT_USER_AGENT"),
)

# Config
SUBREDDIT = "FantasyPL"
FLAIR = "News"
DISCORD_WEBHOOK = os.getenv("DISCORD_FPL_NEWS_WEBHOOK")

# Time window: Yesterday 6 PM → Today 6 PM
now = datetime.now(timezone.utc)
yesterday = now - timedelta(days=1)
start_time = yesterday.replace(hour=18, minute=0, second=0, microsecond=0).timestamp()
end_time = now.replace(hour=18, minute=0, second=0, microsecond=0).timestamp()

print(f"Fetching posts between {datetime.fromtimestamp(start_time, tz=timezone.utc)} "
      f"and {datetime.fromtimestamp(end_time, tz=timezone.utc)}")

def send_to_discord(content: str):
    """Send message to Discord webhook."""
    payload = {"content": content}
    r = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
    r.raise_for_status()

def main():
    found_posts = False
    for submission in reddit.subreddit(SUBREDDIT).search(f'flair:"{FLAIR}"', sort="new", time_filter="day", limit=50):
        created = submission.created_utc
        if start_time <= created < end_time:
            found_posts = True
            msg = f"**{submission.title}**\nhttps://reddit.com{submission.permalink}"
            send_to_discord(msg)
            time.sleep(2)  # avoid spamming Discord too fast

    if not found_posts:
        print("No new posts in the given window.")

if __name__ == "__main__":
    main()
