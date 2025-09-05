import os
import re
import sys
import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Any, Optional, Match

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
    response: requests.Response = requests.get(URL, headers=HEADERS)
    response.raise_for_status()
    html: str = response.text
    soup: BeautifulSoup = BeautifulSoup(html, "html.parser")
    page_text: str = soup.get_text()

    # Split blocks by price line (each player block starts with £)
    blocks: List[str] = re.split(r'\n(?=.*£[0-9.]+)', page_text)
    players_data: List[Dict[str, Any]] = []

    for block in blocks:
        lines: List[str] = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines or '£' not in block:
            continue

        # Find price line
        pos_price_line: str = next((l for l in lines if '£' in l), '')
        price_match: Optional[Match[str]] = re.search(r'£[0-9.]+', pos_price_line)
        price: str = price_match.group(0) if price_match else ''

        # Find position
        pos_match: Optional[Match[str]] = re.search(r'\b(GK|DEF|MID|FW)\b', pos_price_line)
        position: str = pos_match.group(1) if pos_match else ''
        if not position:
            for line in lines:
                if line in ['GK', 'DEF', 'MID', 'FW']:
                    position = line
                    break

        # Find name (line after price line)
        try:
            idx: int = lines.index(pos_price_line)
            name: str = lines[idx + 1] if idx + 1 < len(lines) else ''
        except ValueError:
            name: str = ''

        # Progress, prediction, progress per hour
        prog_matches: List[str] = [l for l in lines if re.match(r'[+-]?[0-9.]+%', l)]
        progress_now: str = prog_matches[0] if len(prog_matches) > 0 else ''
        prediction: str = prog_matches[1] if len(prog_matches) > 1 else ''
        progress_per_hour: str = prog_matches[-1] if len(prog_matches) > 0 else ''

        # Prediction time (e.g., '>2 days', '>5 hours', 'Tonight', 'Tomorrow')
        prediction_time: str = next((l for l in lines if 'day' in l or 'hour' in l or 'Tonight' in l or 'Tomorrow' in l), '')

        # Team
        team_candidates: List[str] = [l for l in lines if l not in [pos_price_line, name, price] 
                           and not re.match(r'[+-]?[0-9.]+%', l) 
                           and 'day' not in l and 'hour' not in l and 'Tonight' not in l and 'Tomorrow' not in l]
        team: str = team_candidates[0] if team_candidates else ''

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

def progress_bar(value: str, total_blocks: int = 20) -> str:
    ori_value: str = value
    numeric_value: float = abs(float(value[:-1]))
    clamped_value: float = min(numeric_value, 100)
    filled_blocks: int = int(clamped_value / 100 * total_blocks)
    empty_blocks: int = total_blocks - filled_blocks
    bar: str = "[" + "-" * filled_blocks + " " * empty_blocks + "]"
    return f"`{bar}` {ori_value}"

def format_message(players_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Format player data into Discord embeds (separate for risers and fallers)."""
    if not players_data:
        return [{
            "title": "📊 Daily LiveFPL Price Predictions",
            "description": "❌ No player data found",
            "color": 0xff0000
        }]

    # Sort by prediction
    players_data.sort(key=lambda x: x['prediction_value'], reverse=True)

    # Top 10 risers and fallers
    risers: List[Dict[str, Any]] = [p for p in players_data if p['prediction_value'] > 0][:10]
    fallers: List[Dict[str, Any]] = [p for p in players_data if p['prediction_value'] < 0]
    fallers.sort(key=lambda x: x['prediction_value'])
    fallers = fallers[:10]

    embeds: List[Dict[str, Any]] = []
    
    # Risers embed
    if risers:
        riser_list: List[str] = []
        for i, p in enumerate(risers, 1):
            riser_list.append(
                f"{i}. **{p['name']}** ({p['position']}) {p['price']} - {p['team']}\n"
                f"{progress_bar(p['progress_now'])}\n"
                f"Pred: {p['prediction']}, Time: {p['prediction_time']}, /hr: {p['progress_per_hour']}"
            )
        
        embeds.append({
            "title": "📊 Daily LiveFPL Price Predictions",
            "fields": [{
                "name": "📈 TOP 10 PREDICTED RISERS",
                "value": '\n\n'.join(riser_list),
                "inline": False
            }],
            "color": 0x2ecc71,  # Green for risers
            "footer": {
                "text": "LiveFPL Price Movement Analysis"
            }
        })

    # Fallers embed
    if fallers:
        faller_list: List[str] = []
        for i, p in enumerate(fallers, 1):
            faller_list.append(
                f"{i}. **{p['name']}** ({p['position']}) {p['price']} - {p['team']}\n"
                f"{progress_bar(p['progress_now'])}\n"
                f"Pred: {p['prediction']}, Time: {p['prediction_time']}, /hr: {p['progress_per_hour']}"
            )
        
        embeds.append({
            "title": "📊 Daily LiveFPL Price Predictions",
            "fields": [{
                "name": "📉 TOP 10 PREDICTED FALLERS",
                "value": '\n\n'.join(faller_list),
                "inline": False
            }],
            "color": 0xe74c3c,  # Red for fallers
            "footer": {
                "text": "LiveFPL Price Movement Analysis"
            }
        })

    return embeds


def send_discord_message(embed_data: Dict[str, Any], webhook_url: str) -> None:
    """Send embed to Discord webhook with field splitting if needed."""
    
    # Check if any field exceeds Discord's 1024 character limit
    for field in embed_data.get('fields', []):
        if len(field['value']) > 1024:
            # Split large fields
            lines = field['value'].split('\n\n')
            current_value: str = ""
            field_parts: List[str] = []
            
            for line in lines:
                if len(current_value) + len(line) + 2 > 1024:  # +2 for \n\n
                    if current_value:
                        field_parts.append(current_value.strip())
                    current_value = line + '\n\n'
                else:
                    current_value += line + '\n\n'
            
            if current_value:
                field_parts.append(current_value.strip())
            
            # Replace original field with split fields
            field_index: int = embed_data['fields'].index(field)
            embed_data['fields'].pop(field_index)

            for i, part in enumerate(field_parts):
                # Original name for first part, zero-width space for continued parts
                part_name: str = field['name'] if i == 0 else "\u200B\u2060"
                part_value: str = part if i == 0 else f"\u00A0\n{part}"  # non-breaking space + newline
                
                embed_data['fields'].insert(field_index + i, {
                    "name": part_name,
                    "value": part_value,
                    "inline": field['inline']
                })

    payload: Dict[str, Any] = {"embeds": [embed_data]}
    
    try:
        discord_response = requests.post(webhook_url, json=payload, timeout=10)
        if discord_response.status_code == 204:
            print("Discord embed sent successfully")
        else:
            print(f"Discord embed failed: {discord_response.status_code}")
    except Exception as e:
        print(f"Discord embed error: {e}")


def send_discord_messages(message: List[Dict[str, Any]], webhook_url: str) -> None:
    """Send Discord messages for risers and fallers separately."""    
    for embed_data in message:
        send_discord_message(embed_data, webhook_url)
        
        # Small delay between messages to avoid rate limiting
        import time
        time.sleep(0.5)

def main() -> None:
    """Main function to run the FPL price prediction script."""
    if not WEBHOOK:
        print("❌ DISCORD_WEBHOOK environment variable not set!")
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