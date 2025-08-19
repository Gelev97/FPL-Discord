# import requests
# import os
# import re
# from bs4 import BeautifulSoup

# WEBHOOK = os.environ.get("DISCORD_WEBHOOK")
# if not WEBHOOK:
#     print("❌ DISCORD_WEBHOOK environment variable not set!")
#     exit(1)

# url = "https://www.livefpl.net/prices"
# headers = {
#     'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
# }

# # Sort by progress percentage (highest first)
# def get_progress_value(player):
#     try:
#         progress_str = player['progress_now'].replace('%', '')
#         return float(progress_str)
#     except:
#         return 0

# def main():
#     try:
#         response = requests.get(url, headers=headers)
#         response.raise_for_status()
#         html = response.text
#         soup = BeautifulSoup(html, "html.parser")

#         # Get the full page text
#         page_text = soup.get_text()
        
#         # The page structure seems to be different - let's look for player data patterns
#         # Based on what I saw, players are listed with format like:
#         # PlayerNamePOS £X.X | Team | X.XX% | X.XX% >2 days | +X.XX%
        
#         players_data = []
#         print(page_text)
    
#         # Look for any text that has player name + position + price pattern
#         player_patterns = re.findall(
#             r'([A-Za-z\'\.\s]+)(GK|DEF|MID|FW)\s*£([\d.]+).*?([-\d.]+%)',
#             page_text,
#             re.DOTALL
#         )
#         print(player_patterns)
#         for pattern in player_patterns:
#             player_name = pattern[0].strip()
#             position = pattern[1]
#             price = pattern[2]
#             progress = pattern[3]
#             print(player_name, position, price, progress)
            
#             # Clean up player name (remove extra text)
#             player_name = re.sub(r'\s+', ' ', player_name).strip()
#             if len(player_name) > 30:  # Probably picked up extra text
#                 player_name = player_name.split()[-1]  # Take last word
            
#             players_data.append({
#                 'name': player_name,
#                 'position': position,
#                 'price': price,
#                 'team': '',
#                 'progress_now': progress,
#                 'prediction': '',
#                 'progress_per_hour': ''
#             })
        
#         players_data.sort(key=get_progress_value, reverse=True)
        
#         if players_data:
#             msg = "📊 Daily Top 10 LiveFPL Price Predictions:\n\n"
            
#             for i, player in enumerate(players_data[:10], 1):
#                 msg += f"{i}. **{player['name']}** {player['position']} £{player['price']}\n"
#                 if player['team']:
#                     msg += f"   🏟️ {player['team']}\n"
#                 msg += f"   📈 Current: {player['progress_now']}\n"
#                 if player['prediction']:
#                     msg += f"   🔮 Prediction: {player['prediction']}\n"
#                 if player['progress_per_hour']:
#                     msg += f"   ⏱️ Per hour: {player['progress_per_hour']}\n"
#                 msg += "\n"
#         else:
#             # Show debug info to understand the page structure
#             msg = "❌ No player data found. Debug info:\n\n"
            
#             # Look for any lines with percentages
#             percentage_lines = []
#             for line in lines:
#                 if '%' in line and re.search(r'[-\d.]+%', line):
#                     percentage_lines.append(line.strip())
            
#             msg += f"Found {len(percentage_lines)} lines with percentages:\n\n"
#             for i, line in enumerate(percentage_lines[:10]):
#                 msg += f"{i+1}. {line[:100]}\n"

#     except requests.RequestException as e:
#         msg = f"❌ Error accessing LiveFPL: {str(e)}"
#         print(f"Request error: {e}")
#     except Exception as e:
#         msg = f"❌ Error parsing LiveFPL data: {str(e)}"
#         print(f"Parsing error: {e}")

#     # Send to Discord
#     try:
#         discord_response = requests.post(WEBHOOK, json={"content": msg})
#         print(f"Discord webhook response: {discord_response.status_code}")
#         print(f"Message length: {len(msg)} characters")
        
#         if discord_response.status_code != 200:
#             print(f"Discord error: {discord_response.text}")
            
#     except Exception as e:
#         print(f"Discord webhook error: {e}")

#     # Always print the message for debugging
#     print("=" * 50)
#     print("MESSAGE CONTENT:")
#     print(msg)
#     print("=" * 50)

# main()

import requests
import os
import re
from bs4 import BeautifulSoup

WEBHOOK = os.environ.get("DISCORD_FPL_INFO_WEBHOOK")
if not WEBHOOK:
    print("❌ DISCORD_WEBHOOK environment variable not set!")
    exit(1)

url = "https://www.livefpl.net/prices"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# Sort by progress percentage (highest first)
def get_progress_value(player):
    try:
        progress_str = player['progress_now'].replace('%', '')
        return float(progress_str)
    except:
        return 0

def main():
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        html = response.text
        soup = BeautifulSoup(html, "html.parser")

        # Get the full page text
        page_text = soup.get_text()
        
        players_data = []
        
        # Use the exact working pattern
        player_patterns = re.findall(
            # r'([A-Za-z\'\.\s]+)(GK|DEF|MID|FW)\s*£([\d.]+)([A-Za-z\'\.\s]+)([A-Za-z\'\.\s]+)([-\d.]+%)([-\d.]+%)([-\d.]+%)(>?\d+\s*days?|Tonight|Tomorrow|[\d.]+\s*hours?)',
            r'([A-Za-z\'\.\s]+)(GK|DEF|MID|FW)\s*£([\d.]+)([A-Za-z\'\.\s]+)([A-Za-z\'\.\s]+).*?([-\d.]+%)([-\d.]+%)',
            page_text,
            re.DOTALL
        )
        
        print(f"Found {len(player_patterns)} player patterns")
        
        for pattern in player_patterns:
            player_name = pattern[0].strip()
            position = pattern[1]
            price = pattern[2]
            team = pattern[4]
            progress = pattern[5]
            prediction = pattern[6]
            progress_per_hour = pattern[7]
            
            # Clean up player name (remove extra text)
            player_name = re.sub(r'\s+', ' ', player_name).strip()
            if len(player_name) > 30:  # Probably picked up extra text
                player_name = player_name.split()[-1]  # Take last word
            
            # Skip very short names
            if len(player_name) < 2:
                continue
            
            players_data.append({
                'name': player_name,
                'position': position,
                'price': price,
                'team': team,
                'progress_now': progress,
                'prediction': prediction,
                'progress_per_hour': progress_per_hour,
                'progress_value': get_progress_value({'progress_now': progress})
            })
            
            print(f"Added: {player_name} {position} £{price} - {progress}")
        
        print(f"Total players found: {len(players_data)}")
        
        if players_data:
            # Sort by progress value
            players_data.sort(key=lambda x: x['progress_value'], reverse=True)
            
            # Get risers (positive progress) and fallers (negative progress)
            risers = [p for p in players_data if p['progress_value'] > 0][:10]
            fallers = [p for p in players_data if p['progress_value'] < 0]
            fallers.sort(key=lambda x: x['progress_value'])  # Most negative first
            fallers = fallers[:10]
            
            msg = "📊 **Daily LiveFPL Price Predictions**\n\n"
            
            # Show top 10 risers
            if risers:
                msg += "📈 **TOP 10 PREDICTED RISERS:**\n\n"
                for i, player in enumerate(risers, 1):
                    msg += f"{i}. **{player['name']}** {player['position']} £{player['price']}\n"
                    msg += f"   📈 Current Progress: {player['progress_now']}\n\n"
            
            # Show top 10 fallers
            if fallers:
                msg += "📉 **TOP 10 PREDICTED FALLERS:**\n\n"
                for i, player in enumerate(fallers, 1):
                    msg += f"{i}. **{player['name']}** {player['position']} £{player['price']}\n"
                    msg += f"   📉 Current Progress: {player['progress_now']}\n\n"
            
            # Add summary
            total_risers = len([p for p in players_data if p['progress_value'] > 0])
            total_fallers = len([p for p in players_data if p['progress_value'] < 0])
            msg += f"📊 **Summary:** {total_risers} risers, {total_fallers} fallers, {len(players_data)} total players"
            
        else:
            msg = "❌ No player data found"

    except requests.RequestException as e:
        msg = f"❌ Error accessing LiveFPL: {str(e)}"
        print(f"Request error: {e}")
    except Exception as e:
        msg = f"❌ Error parsing LiveFPL data: {str(e)}"
        print(f"Parsing error: {e}")

    # Send to Discord
    try:
        # Split message if too long
        if len(msg) > 1900:
            parts = []
            current = ""
            for line in msg.split('\n'):
                if len(current + line + '\n') > 1900:
                    if current:
                        parts.append(current.strip())
                    current = line + '\n'
                else:
                    current += line + '\n'
            if current:
                parts.append(current.strip())
            
            for i, part in enumerate(parts):
                discord_response = requests.post(WEBHOOK, json={"content": part})
                print(f"Discord message {i+1}: {discord_response.status_code}")
        else:
            discord_response = requests.post(WEBHOOK, json={"content": msg})
            print(f"Discord webhook response: {discord_response.status_code}")
        
    except Exception as e:
        print(f"Discord webhook error: {e}")

    print("=" * 50)
    print("MESSAGE CONTENT:")
    print(msg)
    print("=" * 50)

main()