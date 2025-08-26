import os
import re
import sys
import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Any, Optional

WEBHOOK: Optional[str] = os.environ.get("DISCORD_WEBHOOK")
URL: str = "https://www.livefpl.net/prices"
HEADERS: Dict[str, str] = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}


def get_prediction_value(player: Dict[str, Any]) -> float:
    """Extract numeric prediction value from player data."""
    try:
        return float(player['prediction'].replace('%', ''))
    except (ValueError, KeyError, AttributeError):
        return 0.0


def fetch_price_data() -> List[Dict[str, Any]]:
    """Fetch and parse player price data from LiveFPL."""
    response = requests.get(URL, headers=HEADERS)
    response.raise_for_status()
    html = response.text
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text()

    # Split blocks by price line (each player block starts with £)
    blocks = re.split(r'\n(?=.*£[0-9.]+)', page_text)
    players_data: List[Dict[str, Any]] = []

    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines or '£' not in block:
            continue

        # Find price line
        pos_price_line = next((l for l in lines if '£' in l), '')
        price_match = re.search(r'£[0-9.]+', pos_price_line)
        price = price_match.group(0) if price_match else ''

        # Find position
        pos_match = re.search(r'\b(GK|DEF|MID|FW)\b', pos_price_line)
        position = pos_match.group(1) if pos_match else ''
        if not position:
            for line in lines:
                if line in ['GK', 'DEF', 'MID', 'FW']:
                    position = line
                    break

        # Find name (line after price line)
        try:
            idx = lines.index(pos_price_line)
            name = lines[idx + 1] if idx + 1 < len(lines) else ''
        except ValueError:
            name = ''

        # Progress, prediction, progress per hour
        prog_matches = [l for l in lines if re.match(r'[+-]?[0-9.]+%', l)]
        progress_now = prog_matches[0] if len(prog_matches) > 0 else ''
        prediction = prog_matches[1] if len(prog_matches) > 1 else ''
        progress_per_hour = prog_matches[-1] if len(prog_matches) > 0 else ''

        # Prediction time (e.g., '>2 days', '>5 hours', 'Tonight', 'Tomorrow')
        prediction_time = next((l for l in lines if 'day' in l or 'hour' in l or 'Tonight' in l or 'Tomorrow' in l), '')

        # Team
        team_candidates = [l for l in lines if l not in [pos_price_line, name, price] 
                           and not re.match(r'[+-]?[0-9.]+%', l) 
                           and 'day' not in l and 'hour' not in l and 'Tonight' not in l and 'Tomorrow' not in l]
        team = team_candidates[0] if team_candidates else ''

        players_data.append({
            'name': name,
            'position': position,
            'price': price,
            'team': team,
            'progress_now': progress_now,
            'prediction': prediction,
            'prediction_time': prediction_time,
            'progress_per_hour': progress_per_hour,
            'prediction_value': get_prediction_value({'prediction': prediction})
        })

    return players_data


def format_message(players_data: List[Dict[str, Any]]) -> str:
    """Format player data into Discord message."""
    if not players_data:
        return "❌ No player data found"

    # Sort by prediction
    players_data.sort(key=lambda x: x['prediction_value'], reverse=True)

    # Top 10 risers and fallers
    risers = [p for p in players_data if p['prediction_value'] > 0][:10]
    fallers = [p for p in players_data if p['prediction_value'] < 0]
    fallers.sort(key=lambda x: x['prediction_value'])
    fallers = fallers[:10]

    # Compose message
    msg = "📊 **Daily LiveFPL Price Predictions**\n\n"

    msg += "📈 **TOP 10 PREDICTED RISERS:**\n\n"
    for i, p in enumerate(risers, 1):
        msg += (
            f"{i}. **{p['name']}** ({p['position']}) {p['price']} - {p['team']}\n"
            f"   Progress Now📈: {p['progress_now']}, Prediction: {p['prediction']}, "
            f"Prediction Time: {p['prediction_time']}, Progress/hr: {p['progress_per_hour']}\n"
        )

    msg += "\n📉 **TOP 10 PREDICTED FALLERS:**\n\n"
    for i, p in enumerate(fallers, 1):
        msg += (
            f"{i}. **{p['name']}** ({p['position']}) {p['price']} - {p['team']}\n"
            f"   Progress Now📉: {p['progress_now']}, Prediction: {p['prediction']}, "
            f"Prediction Time: {p['prediction_time']}, Progress/hr: {p['progress_per_hour']}\n"
        )

    return msg


def send_discord_message(message: str, webhook_url: str) -> None:
    """Send message to Discord webhook in chunks if needed."""
    # Discord-safe splitting
    parts: List[str] = []
    current = ""
    for block in message.split("\n\n"):
        block_with_newline = block + "\n\n"
        if len(current) + len(block_with_newline) > 1900:
            parts.append(current.strip())
            current = block_with_newline
        else:
            current += block_with_newline
    if current:
        parts.append(current.strip())

    for i, part in enumerate(parts):
        discord_response = requests.post(webhook_url, json={"content": part})
        print(f"Discord message {i+1}: {discord_response.status_code}")


def main() -> None:
    """Main function to run the FPL price prediction script."""
    if not WEBHOOK:
        print("❌ DISCORD_WEBHOOK environment variable not set!")
        sys.exit(1)

    try:
        players_data = fetch_price_data()
        message = format_message(players_data)
        send_discord_message(message, WEBHOOK)
    except requests.RequestException as e:
        print(f"Request error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Parsing error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()