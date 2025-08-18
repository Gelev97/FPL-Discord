import requests
import os
from bs4 import BeautifulSoup

WEBHOOK = os.environ["DISCORD_WEBHOOK"]

url = "https://www.livefpl.net/prices"
html = requests.get(url).text
soup = BeautifulSoup(html, "html.parser")

# Find the main table with player data
table = soup.find("table")
if not table:
    print("Table not found")
    exit()

# Get all rows except header
rows = table.find_all("tr")[1:]  # Skip header row

msg = "📊 Daily Top 10 LiveFPL Price Predictions:\n\n"

# Get first 10 players
for i, row in enumerate(rows[:10], 1):
    cols = row.find_all("td")
    if len(cols) >= 4:  # Ensure we have enough columns
        # Extract player name (usually first column with text)
        player_cell = cols[0]
        player_name = player_cell.get_text(strip=True)
        
        # Extract current progress (column 1)
        progress_now = cols[1].get_text(strip=True) if len(cols) > 1 else "N/A"
        
        # Extract prediction (column 2) 
        prediction = cols[2].get_text(strip=True) if len(cols) > 2 else "N/A"
        
        # Extract progress per hour (column 3)
        progress_per_hour = cols[3].get_text(strip=True) if len(cols) > 3 else "N/A"
        
        # Clean up the player name (remove extra whitespace)
        player_name = ' '.join(player_name.split())
        
        msg += f"{i}. **{player_name}**\n"
        msg += f"   📈 Now: {progress_now} | Prediction: {prediction}\n"
        msg += f"   ⏱️ Per hour: {progress_per_hour}\n\n"

# Fallback if no data found
if len(rows) == 0:
    msg = "❌ No price prediction data found on LiveFPL"

# Send to Discord
response = requests.post(WEBHOOK, json={"content": msg})
print(f"Discord webhook response: {response.status_code}")
print(f"Message sent: {msg[:100]}...")  # Print first 100 chars for debugging
