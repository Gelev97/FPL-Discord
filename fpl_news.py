import os
import time
import praw
import requests
from datetime import datetime, timedelta, timezone
from typing import Optional

def send_to_discord(content: str, webhook_url: str) -> None:
    """Send message to Discord webhook."""
    try:
        payload = {"content": content}
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Failed to send message to Discord: {e}")
        raise

def main() -> None:
    """Main function to fetch FPL news from Reddit and send to Discord."""
    # Reddit setup
    reddit = praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        user_agent=os.getenv("REDDIT_USER_AGENT"),
    )

    # Config
    subreddit_name = "FantasyPL"
    flair = "News"
    discord_webhook = os.getenv("DISCORD_WEBHOOK")
    
    if not discord_webhook:
        print("Error: DISCORD_WEBHOOK environment variable not set")
        return

    # Time window: Yesterday 6 PM → Today 6 PM
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    start_time = yesterday.replace(hour=18, minute=0, second=0, microsecond=0).timestamp()
    end_time = now.replace(hour=18, minute=0, second=0, microsecond=0).timestamp()

    print(f"Fetching posts between {datetime.fromtimestamp(start_time, tz=timezone.utc)} "
          f"and {datetime.fromtimestamp(end_time, tz=timezone.utc)}")

    try:
        found_posts = False
        for submission in reddit.subreddit(subreddit_name).search(
            f'flair:"{flair}"', sort="new", time_filter="day", limit=50
        ):
            created = submission.created_utc
            if start_time <= created < end_time:
                found_posts = True
                msg = f"**{submission.title}**\nhttps://reddit.com{submission.permalink}"
                send_to_discord(msg, discord_webhook)
                time.sleep(2)  # avoid spamming Discord too fast

        if not found_posts:
            print("No new posts in the given window.")
    except Exception as e:
        print(f"Error fetching Reddit posts: {e}")
        raise

if __name__ == "__main__":
    main()
