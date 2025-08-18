import requests, os
from bs4 import BeautifulSoup

WEBHOOK = os.environ["DISCORD_WEBHOOK"]

url = "https://www.livefpl.net/prices"
html = requests.get(url).text
soup = BeautifulSoup(html, "html.parser")

rows = soup.select("table tr")[1:11]  # top 10 players
msg = "📊 Daily Top 10 LiveFPL Prices:\n"
for i, row in enumerate(rows, 1):
    cols = [c.get_text(strip=True) for c in row.find_all("td")]
    if cols:
        player, progress = cols[0], cols[-1]
        msg += f"{i}. {player} - {progress}\n"

requests.post(WEBHOOK, json={"content": msg})
