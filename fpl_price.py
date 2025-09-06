"""Fantasy Premier League price prediction fetcher and Discord notifier.

This module scrapes player price change predictions from LiveFPL website and sends
formatted reports to Discord via webhook. It identifies the top 10 predicted price
risers and fallers, displaying them in rich embeds with progress bars and detailed
prediction information.

The module performs web scraping of LiveFPL"s price prediction data, parses player
information including current progress, predictions, and timing estimates, then
formats the data into Discord embeds for easy consumption by FPL managers.

Typical usage example:

    python fpl_price.py

Environment variables required:
    DISCORD_WEBHOOK: Discord webhook URL for sending price prediction reports
"""

import os
import re
import sys
import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Any, Optional, Match

WEBHOOK = os.environ.get("DISCORD_WEBHOOK")
URL = "https://www.livefpl.net/prices"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
}

def get_prediction_value(player: Dict[str, Any]) -> float:
    """Extract numeric prediction value from player data.

    Converts a prediction percentage string (e.g., "75%", "-25%") to a float value
    for sorting and comparison purposes.

    Args:
        player: Dictionary containing player data with "prediction" key.

    Returns:
        Float value of the prediction percentage. Returns 0.0 if extraction fails.

    Example:
        >>> get_prediction_value({"prediction": "75%"})
        75.0
        >>> get_prediction_value({"prediction": "-25%"})
        -25.0
    """
    try:
        return float(player["prediction"].replace("%", ""))
    except (ValueError, KeyError, AttributeError):
        return 0.0

def fetch_price_data() -> List[Dict[str, Any]]:
    """Fetch and parse player price prediction data from LiveFPL website.

    Scrapes the LiveFPL prices page and extracts detailed player information including
    names, positions, prices, teams, current progress, predictions, and timing data.
    Uses regex patterns to parse the unstructured text data from the webpage.

    Returns:
        List of dictionaries containing parsed player data. Each dictionary includes:
        - name: Player name
        - position: Player position (GK, DEF, MID, FW)
        - price: Current player price (e.g., "£8.5")
        - team: Player"s team name
        - progress_now: Current price change progress percentage
        - prediction: Predicted final percentage for price change
        - prediction_time: Time estimate for price change (e.g., "Tonight", ">2 days")
        - progress_per_hour: Rate of progress per hour
        - prediction_value: Numeric value of prediction for sorting

    Raises:
        requests.HTTPError: If the HTTP request to LiveFPL fails.
        Exception: If HTML parsing or data extraction fails.

    Example:
        >>> data = fetch_price_data()
        >>> data[0]["name"]
        "Salah"
        >>> data[0]["prediction"]
        "75%"
    """
    response = requests.get(URL, headers=HEADERS)
    response.raise_for_status()
    html = response.text
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text()

    # Split blocks by price line (each player block starts with £)
    blocks = re.split(r"\n(?=.*£[0-9.]+)", page_text)
    players_data = []

    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines or "£" not in block:
            continue

        # Find price line
        pos_price_line = next((l for l in lines if "£" in l), "")
        price_match = re.search(r"£[0-9.]+", pos_price_line)
        price = price_match.group(0) if price_match else ""

        # Find position
        pos_match = re.search(r"\b(GK|DEF|MID|FW)\b", pos_price_line)
        position = pos_match.group(1) if pos_match else ""
        if not position:
            for line in lines:
                if line in ["GK", "DEF", "MID", "FW"]:
                    position = line
                    break

        # Find name (line after price line)
        try:
            idx = lines.index(pos_price_line)
            name = lines[idx + 1] if idx + 1 < len(lines) else ""
        except ValueError:
            name = ""

        # Progress, prediction, progress per hour
        prog_matches = [l for l in lines if re.match(r"[+-]?[0-9.]+%", l)]
        progress_now = prog_matches[0] if len(prog_matches) > 0 else ""
        prediction = prog_matches[1] if len(prog_matches) > 1 else ""
        progress_per_hour = prog_matches[-1] if len(prog_matches) > 0 else ""

        # Prediction time (e.g., ">2 days", ">5 hours", "Tonight", "Tomorrow")
        prediction_time = next((l for l in lines if "day" in l or "hour" in l or "Tonight" in l or "Tomorrow" in l), "")

        # Team
        team_candidates = [l for l in lines if l not in [pos_price_line, name, price]
                           and not re.match(r"[+-]?[0-9.]+%", l)
                           and "day" not in l and "hour" not in l and "Tonight" not in l and "Tomorrow" not in l]
        team= team_candidates[0] if team_candidates else ""

        players_data.append({
            "name": name,
            "position": position,
            "price": price,
            "team": team,
            "progress_now": progress_now,
            "prediction": prediction,
            "prediction_time": prediction_time,
            "progress_per_hour": progress_per_hour,
            "prediction_value": get_prediction_value({"prediction": prediction})
        })

    return players_data

def progress_bar(value: str, total_blocks: int = 20) -> str:
    """Generate a visual progress bar for percentage values.

    Creates a text-based progress bar representation of a percentage value,
    using filled blocks (-) and empty spaces to show progress visually.

    Args:
        value: Percentage string (e.g., "75%", "-25%").
        total_blocks: Total number of blocks in the progress bar. Defaults to 20.

    Returns:
        Formatted string containing the progress bar and original value.
        Format: "`[-------- ]` 75%"

    Example:
        >>> progress_bar("75%")
        "`[--------------- ]` 75%"
        >>> progress_bar("25%", 10)
        "`[--        ]` 25%"
    """
    ori_value = value
    numeric_value = abs(float(value[:-1]))
    clamped_value = min(numeric_value, 100)
    filled_blocks = int(clamped_value / 100 * total_blocks)
    empty_blocks = total_blocks - filled_blocks
    bar = "[" + "-" * filled_blocks + " " * empty_blocks + "]"
    return f"`{bar}` {ori_value}"

def format_message(players_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Format player data into Discord embeds for risers and fallers.

    Processes player data to create separate Discord embeds for the top 10 predicted
    price risers and fallers. Each embed includes formatted player information with
    progress bars, predictions, and timing estimates.

    Args:
        players_data: List of dictionaries containing player information from fetch_price_data().

    Returns:
        List of Discord embed dictionaries. Returns up to 2 embeds:
        - One for risers (green color, players with positive predictions)
        - One for fallers (red color, players with negative predictions)
        Returns error embed if no data is provided.

    Example:
        >>> data = [{"name": "Salah", "prediction_value": 75.0, ...}]
        >>> embeds = format_message(data)
        >>> len(embeds)
        1
        >>> embeds[0]["color"]
        3066993  # Green color for risers
    """
    if not players_data:
        return [{
            "title": "📊 Daily LiveFPL Price Predictions",
            "description": "❌ No player data found",
            "color": 0xff0000
        }]

    # Sort by prediction
    players_data.sort(key=lambda x: x["prediction_value"], reverse=True)

    # Top 10 risers and fallers
    risers = [p for p in players_data if p["prediction_value"] > 0][:10]
    fallers = [p for p in players_data if p["prediction_value"] < 0]
    fallers.sort(key=lambda x: x["prediction_value"])
    fallers = fallers[:10]

    embeds = []

    # Risers embed
    if risers:
        riser_list = []
        for i, p in enumerate(risers, 1):
            riser_list.append(
                f'{i}. **{p["name"]}** ({p["position"]}) {p["price"]} - {p["team"]}\n'
                f'{progress_bar(p["progress_now"])}\n'
                f'Pred: {p["prediction"]}, Time: {p["prediction_time"]}, /hr: {p["progress_per_hour"]}'
            )

        embeds.append({
            "title": "📊 Daily LiveFPL Price Predictions",
            "fields": [{
                "name": "📈 TOP 10 PREDICTED RISERS",
                "value": "\n\n".join(riser_list),
                "inline": False
            }],
            "color": 0x2ecc71,  # Green for risers
            "footer": {
                "text": "LiveFPL Price Movement Analysis"
            }
        })

    # Fallers embed
    if fallers:
        faller_list = []
        for i, p in enumerate(fallers, 1):
            faller_list.append(
                f'{i}. **{p["name"]}** ({p["position"]}) {p["price"]} - {p["team"]}\n'
                f'{progress_bar(p["progress_now"])}\n'
                f'Pred: {p["prediction"]}, Time: {p["prediction_time"]}, /hr: {p["progress_per_hour"]}'
            )

        embeds.append({
            "title": "📊 Daily LiveFPL Price Predictions",
            "fields": [{
                "name": "📉 TOP 10 PREDICTED FALLERS",
                "value": "\n\n".join(faller_list),
                "inline": False
            }],
            "color": 0xe74c3c,  # Red for fallers
            "footer": {
                "text": "LiveFPL Price Movement Analysis"
            }
        })

    return embeds

def send_discord_message(embed_data: Dict[str, Any], webhook_url: str) -> None:
    """Send an embed to Discord webhook with automatic field splitting.

    Posts a Discord embed via webhook, automatically splitting fields that exceed
    Discord"s 1024 character limit into multiple fields to ensure successful delivery.

    Args:
        embed_data: Dictionary containing Discord embed data with fields, title, color, etc.
        webhook_url: Discord webhook URL to send the embed to.

    Note:
        Fields exceeding 1024 characters are automatically split at logical boundaries
        (double newlines) to maintain formatting while respecting Discord"s limits.
        Continuation fields use zero-width space characters for seamless appearance.

    Raises:
        Exception: If the webhook request fails or times out.
    """

    # Check if any field exceeds Discord"s 1024 character limit
    for field in embed_data.get("fields", []):
        if len(field["value"]) > 1024:
            # Split large fields
            lines = field["value"].split("\n\n")
            current_value = ""
            field_parts = []

            for line in lines:
                if len(current_value) + len(line) + 2 > 1024:  # +2 for \n\n
                    if current_value:
                        field_parts.append(current_value.strip())
                    current_value = line + "\n\n"
                else:
                    current_value += line + "\n\n"

            if current_value:
                field_parts.append(current_value.strip())

            # Replace original field with split fields
            field_index = embed_data["fields"].index(field)
            embed_data["fields"].pop(field_index)

            for i, part in enumerate(field_parts):
                # Original name for first part, zero-width space for continued parts
                part_name = field["name"] if i == 0 else "\u200B\u2060"
                part_value = part if i == 0 else f"\u00A0\n{part}"  # non-breaking space + newline

                embed_data["fields"].insert(field_index + i, {
                    "name": part_name,
                    "value": part_value,
                    "inline": field["inline"]
                })

    payload = {"embeds": [embed_data]}

    try:
        discord_response = requests.post(webhook_url, json=payload, timeout=10)
        if discord_response.status_code == 204:
            print("Discord embed sent successfully")
        else:
            print(f"Discord embed failed: {discord_response.status_code}")
    except Exception as e:
        print(f"Discord embed error: {e}")

def send_discord_messages(message: List[Dict[str, Any]], webhook_url: str) -> None:
    """Send multiple Discord embeds sequentially with rate limiting.

    Sends a list of Discord embeds to a webhook URL with appropriate delays
    between messages to avoid rate limiting from Discord"s API.

    Args:
        message: List of Discord embed dictionaries to send.
        webhook_url: Discord webhook URL for sending messages.

    Note:
        Includes a 0.5-second delay between messages to prevent rate limiting.
        Each embed is sent individually to ensure proper delivery.
    """
    for embed_data in message:
        send_discord_message(embed_data, webhook_url)

        # Small delay between messages to avoid rate limiting
        import time
        time.sleep(0.5)

def main() -> None:
    """Execute the FPL price prediction workflow.

    Orchestrates the complete process of fetching price data from LiveFPL,
    formatting it into Discord embeds, and sending them via webhook. Handles
    environment variable validation and error management.

    The workflow consists of:
    1. Validate required environment variables
    2. Fetch and parse price prediction data from LiveFPL
    3. Format data into Discord embeds (separate for risers/fallers)
    4. Send formatted embeds to Discord webhook

    Raises:
        SystemExit: If DISCORD_WEBHOOK environment variable is not set,
                   or if critical errors occur during execution.

    Environment Variables:
        DISCORD_WEBHOOK: Required Discord webhook URL for sending reports.
    """
    if not WEBHOOK:
        print("DISCORD_WEBHOOK environment variable not set!")
        sys.exit(1)

    try:
        players_data = fetch_price_data()
        message = format_message(players_data)
        send_discord_messages(message, WEBHOOK)
    except requests.RequestException as e:
        print(f"Request error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Parsing error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()