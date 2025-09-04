import os
import re
import sys
import requests
from bs4 import BeautifulSoup
from datetime import datetime
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


def create_player_field(players: List[Dict[str, Any]], title: str) -> Dict[str, Any]:
    """Create a Discord embed field for players."""
    if not players:
        return {"name": title, "value": "No players found", "inline": False}
    
    value_lines = []
    for i, p in enumerate(players[:10], 1):  # Limit to top 10
        line = (f"{i}. **{p['name']}** ({p['position']}) {p['price']} - {p['team']}\n"
                f"   Now: {p['progress_now']}, Pred: {p['prediction']}, "
                f"Time: {p['prediction_time']}")
        value_lines.append(line)
    
    # Discord field value limit is 1024 characters
    value = "\n\n".join(value_lines)
    if len(value) > 1024:
        # Truncate and add indicator
        value = value[:1000] + "...\n*(truncated)*"
    
    return {"name": title, "value": value, "inline": False}


def send_discord_embeds(players_data: List[Dict[str, Any]], webhook_url: str) -> None:
    """Send FPL data as Discord embeds."""
    if not players_data:
        # Send error embed
        embed = {
            "title": "FPL Price Predictions",
            "description": "No player data found",
            "color": 0xe74c3c,  # Red
            "timestamp": datetime.now().isoformat()
        }
        payload = {"embeds": [embed]}
        requests.post(webhook_url, json=payload)
        return

    # Sort players
    players_data.sort(key=lambda x: x['prediction_value'], reverse=True)
    
    # Get risers and fallers
    risers = [p for p in players_data if p['prediction_value'] > 0]
    fallers = [p for p in players_data if p['prediction_value'] < 0]
    fallers.sort(key=lambda x: x['prediction_value'])

    # Create main embed
    embed = {
        "title": "Daily FPL Price Predictions",
        "description": f"Top predicted price changes from LiveFPL",
        "color": 0x2ecc71,  # Green
        "thumbnail": {
            "url": "https://fantasy.premierleague.com/static/favicon/favicon-32x32.png"
        },
        "fields": [],
        "footer": {
            "text": "Data from LiveFPL.net",
            "icon_url": "https://fantasy.premierleague.com/static/favicon/favicon-16x16.png"
        },
        "timestamp": datetime.now().isoformat()
    }

    # Add risers field
    if risers:
        risers_field = create_player_field(risers[:5], "📈 Top 5 Predicted Risers")
        embed["fields"].append(risers_field)

    # Add fallers field  
    if fallers:
        fallers_field = create_player_field(fallers[:5], "📉 Top 5 Predicted Fallers")
        embed["fields"].append(fallers_field)

    # Add summary field
    summary_value = f"Total Risers: {len(risers)}\nTotal Fallers: {len(fallers)}\nData Points: {len(players_data)}"
    embed["fields"].append({
        "name": "Summary",
        "value": summary_value,
        "inline": True
    })

    # Send main embed
    payload = {"embeds": [embed]}
    
    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        if response.status_code == 204:
            print("Discord embed sent successfully")
        else:
            print(f"Discord embed failed: {response.status_code}")
    except Exception as e:
        print(f"Discord embed error: {e}")

    # If there are more than 5 risers/fallers, send additional embeds
    if len(risers) > 5:
        send_additional_embed(risers[5:10], "📈 More Predicted Risers (6-10)", 0x27ae60, webhook_url)
    
    if len(fallers) > 5:
        send_additional_embed(fallers[5:10], "📉 More Predicted Fallers (6-10)", 0xe67e22, webhook_url)


def send_additional_embed(players: List[Dict[str, Any]], title: str, color: int, webhook_url: str) -> None:
    """Send additional embed for extended player lists."""
    if not players:
        return
    
    field = create_player_field(players, title)
    
    embed = {
        "title": title,
        "color": color,
        "fields": [field],
        "timestamp": datetime.now().isoformat()
    }
    
    payload = {"embeds": [embed]}
    
    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        if response.status_code == 204:
            print(f"Additional embed sent: {title}")
        else:
            print(f"Additional embed failed: {response.status_code}")
    except Exception as e:
        print(f"Additional embed error: {e}")


def send_discord_message(message: str, webhook_url: str) -> None:
    """Fallback method for simple text messages (kept for compatibility)."""
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
        send_discord_embeds(players_data, WEBHOOK)
    except requests.RequestException as e:
        print(f"Request error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Parsing error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()