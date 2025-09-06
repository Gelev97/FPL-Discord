"""Fantasy Premier League news fetcher and Discord notifier.

This module fetches Fantasy Premier League news posts from the FantasyPL subreddit
and sends them to a Discord channel via webhook. It monitors posts with the "News"
flair within a specific time window (yesterday 6 PM to today 6 PM) and forwards
them to Discord with proper formatting.

Typical usage example:

    python fpl_news.py

Environment variables required:
    REDDIT_CLIENT_ID: Reddit API client ID
    REDDIT_CLIENT_SECRET: Reddit API client secret
    REDDIT_USER_AGENT: Reddit API user agent string
    DISCORD_WEBHOOK: Discord webhook URL for sending messages
"""

import os
import time
import praw
import requests
from datetime import datetime, timedelta, timezone

def send_to_discord(content: str, webhook_url: str) -> None:
    """Send a message to a Discord channel via webhook.

    Posts a message to Discord using the provided webhook URL. The message is sent
    as a JSON payload with a timeout of 10 seconds.

    Args:
        content: The message content to send to Discord.
        webhook_url: The Discord webhook URL to post the message to.

    Raises:
        requests.RequestException: If the webhook request fails or times out.
    """
    try:
        payload = {"content": content}
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Failed to send message to Discord: {e}")
        raise

def main() -> None:
    """Fetch FPL news from Reddit and send to Discord.

    Searches the FantasyPL subreddit for posts with "News" flair within a 24-hour
    window (yesterday 6 PM to today 6 PM UTC) and forwards them to Discord via
    webhook. Posts are sent with their title and Reddit permalink.

    The function performs the following steps:
    1. Initializes Reddit API connection using environment variables
    2. Defines time window for post filtering
    3. Searches for posts with "News" flair in the specified timeframe
    4. Sends formatted messages to Discord with 2-second delays between posts

    Raises:
        Exception: If Reddit API connection fails or Discord webhook sending fails.

    Environment Variables:
        REDDIT_CLIENT_ID: Reddit API client ID
        REDDIT_CLIENT_SECRET: Reddit API client secret
        REDDIT_USER_AGENT: Reddit API user agent string
        DISCORD_WEBHOOK: Discord webhook URL for notifications
    """
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
