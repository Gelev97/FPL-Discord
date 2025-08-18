import requests
import os
import re
from bs4 import BeautifulSoup

WEBHOOK = os.environ["DISCORD_WEBHOOK"]

url = "https://www.livefpl.net/prices"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

try:
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    html = response.text
    soup = BeautifulSoup(html, "html.parser")

    # Look for the table structure
    table = soup.find("table")
    
    if not table:
        msg = "❌ Could not find price prediction table"
    else:
        # Get all rows from the table
        rows = table.find_all("tr")
        
        msg = "📊 Daily Top 10 LiveFPL Price Predictions:\n\n"
        count = 0
        
        for row in rows:
            if count >= 10:
                break
                
            # Look for rows with player data (should have multiple td elements)
            cols = row.find_all("td")
            
            # Need at least 5 columns: Player, Progress Now, Prediction, Time, Progress per hr
            if len(cols) >= 5:
                # Extract player info from first column
                player_col = cols[0]
                player_text = player_col.get_text(strip=True)
                
                # Extract progress from appropriate columns
                progress_now = cols[1].get_text(strip=True)
                prediction = cols[2].get_text(strip=True)
                time_estimate = cols[3].get_text(strip=True)
                progress_per_hour = cols[4].get_text(strip=True)
                
                # Parse player name - it's usually in format "PlayerNamePOS £X.X"
                # Remove position and price info
                player_name = re.sub(r'(GK|DEF|MID|FW)\s*£[\d.]+.*, '', player_text).strip()
                
                # Also try removing just the price part
                if not player_name:
                    player_name = re.sub(r'£[\d.]+.*, '', player_text).strip()
                
                # Clean up any remaining artifacts
                player_name = re.sub(r'\s+', ' ', player_name).strip()
                
                # Skip if we couldn't extract a valid player name
                if not player_name or len(player_name) < 2:
                    continue
                
                # Skip if progress data doesn't look like percentages
                if not re.search(r'[\d.-]+%', progress_now):
                    continue
                
                count += 1
                
                # Format the output
                msg += f"{count}. **{player_name}**\n"
                msg += f"   📈 Current: {progress_now}\n"
                msg += f"   🔮 Prediction: {prediction}\n"
                msg += f"   ⏰ Time: {time_estimate}\n"
                msg += f"   ⏱️ Per hour: {progress_per_hour}\n\n"
        
        # If no data found, provide debug info
        if count == 0:
            msg = "❌ Debug - Table structure analysis:\n\n"
            msg += f"Found table with {len(rows)} rows\n\n"
            
            # Show structure of first few rows
            for i, row in enumerate(rows[:3]):
                cols = row.find_all(['td', th'])
                msg += f"Row {i}: {len(cols)} columns\n"
                for j, col in enumerate(cols[:5]):
                    text = col.get_text(strip=True)[:30]
                    msg += f"  [{j}]: {text}\n"
                msg += "\n"

except requests.RequestException as e:
    msg = f"❌ Error accessing LiveFPL: {str(e)}"
    print(f"Request error: {e}")
except Exception as e:
    msg = f"❌ Error parsing LiveFPL data: {str(e)}"
    print(f"Parsing error: {e}")

# Send to Discord
try:
    discord_response = requests.post(WEBHOOK, json={"content": msg})
    print(f"Discord webhook response: {discord_response.status_code}")
    print(f"Message length: {len(msg)} characters")
    
    if discord_response.status_code != 200:
        print(f"Discord error: {discord_response.text}")
        
except Exception as e:
    print(f"Discord webhook error: {e}")

# Always print the message for debugging
print("=" * 50)
print("MESSAGE CONTENT:")
print(msg)
print("=" * 50)
