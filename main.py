import os
import json
import requests
import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load environment variables (API keys)
load_dotenv()

# Configuration
CONFIG_PATH = "sources.json"
MEMORY_PATH = "memory.json"
PLAYER_DATA_PATH = "player_data.json"
FPL_API_URL = "https://fantasy.premierleague.com/api/"

def get_fpl_stats():
    """Fetches player stats and fixtures, updating a local file weekly."""
    needs_update = True
    if os.path.exists(PLAYER_DATA_PATH):
        last_modified = datetime.datetime.fromtimestamp(os.path.getmtime(PLAYER_DATA_PATH))
        if datetime.datetime.now() - last_modified < datetime.timedelta(days=7):
            needs_update = False
            try:
                with open(PLAYER_DATA_PATH, 'r') as f:
                    return json.load(f)
            except:
                needs_update = True

    if needs_update:
        try:
            # 1. Fetch main bootstrap data
            response = requests.get(f"{FPL_API_URL}bootstrap-static/")
            data = response.json()
            
            # 2. Fetch Fixtures to calculate Difficulty (FDR)
            fixtures_res = requests.get(f"{FPL_API_URL}fixtures/")
            fixtures_data = fixtures_res.json()
            
            # Identify current gameweek
            current_gw = next(gw for gw in data['events'] if gw['is_current'])['id']
            next_gws = [current_gw + 1, current_gw + 2, current_gw + 3]
            
            # Map Team IDs to Names
            teams = {t['id']: t['name'] for t in data['teams']}
            
            # Calculate Team FDR for next 3 GWs
            team_fdr = {t_id: 0 for t_id in teams.keys()}
            for f in fixtures_data:
                if f['event'] in next_gws:
                    team_fdr[f['team_h']] += f['team_h_difficulty']
                    team_fdr[f['team_a']] += f['team_a_difficulty']
            
            # 3. Process Player Stats (Form, xG, ICT)
            players = data['elements']
            
            # Top 5 by ICT Index (Influence, Creativity, Threat)
            top_ict = sorted(players, key=lambda x: float(x['ict_index']), reverse=True)[:10]
            ict_data = [{ "name": p['web_name'], "ict": p['ict_index'], "xG": p['expected_goals']} for p in top_ict]
            
            # Top 5 by Form
            top_form = sorted(players, key=lambda x: float(x['form']), reverse=True)[:10]
            form_data = [{"name": p['web_name'], "form": p['form'], "price": p['now_cost']/10} for p in top_form]
            
            # Best Fixtures (Next 3 GWs)
            best_teams = sorted(team_fdr.items(), key=lambda x: x[1])[:5]
            fixture_data = [{"team": teams[t_id], "fdr": score} for t_id, score in best_teams]
            
            stats_package = {
                "last_updated": str(datetime.date.today()),
                "top_form": form_data,
                "top_threat": ict_data,
                "best_fixtures": fixture_data
            }
            
            with open(PLAYER_DATA_PATH, 'w') as f:
                json.dump(stats_package, f, indent=2)
                
            return stats_package
        except Exception as e:
            print(f"Error fetching FPL stats: {e}")
            return None

def gather_news_with_gemini(sources_config, memory_context):
    """Uses Gemini to search for NEW FPL news, avoiding duplicates."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "Gemini API key missing. Skipping news gathering."
    
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    Search for the latest FPL news from these sources: 
    {', '.join(sources_config['twitter_handles'])} and {', '.join(sources_config['websites'])}.
    
    HISTORICAL CONTEXT (What you already reported recently):
    {memory_context}
    
    INSTRUCTIONS:
    Identify only NEW developments that haven't been covered in the historical context above.
    Focus on:
    1. Breaking injury news (focus on @BenDinnery).
    2. Predicted lineups/benchings for the current gameweek.
    3. Captaincy sentiment on Twitter (#FPL).
    4. Any blank/double gameweek news (focus on @BenCrellin).
    
    Provide a concise summary in 5-7 bullet points. If no new info is found, state that briefly.
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        return response.text
    except Exception as e:
        return f"Error gathering news: {e}"

def get_gemini_reasoning(news, stats, memory_context):
    """Uses Gemini as the 'Lead Analyst' to reason over stats, news, and history."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "Gemini API key missing. Cannot provide reasoning."
    
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    You are the Lead FPL Strategist. 
    
    HISTORICAL CONTEXT (Last 7 Days):
    {memory_context}
    
    TODAY'S LATEST NEWS:
    {news}
    
    CURRENT PLAYER DATA (INTERNAL SUPPORT):
    {json.dumps(stats, indent=2)}
    
    MISSION:
    Based on the trends and today's breaking news, provide:
    1. **The 'Must-Buy' Player:** (Who is the priority transfer?)
    2. **The 'Panic-Sell' Player:** (Who is a trap or injured?)
    3. **Captaincy Verdict:** (The top choice and a 'brave' differential.)
    4. **Long-term Outlook:** (How should we prepare for upcoming gameweeks?)
    
    Be decisive and use a professional, data-driven tone. DO NOT list the raw player stats in your final output; use them only to support your reasoning.
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-1.5-pro",
            contents=prompt
        )
        return response.text
    except Exception as e:
        return f"Error in Gemini reasoning: {e}"


def update_memory(new_summary):
    """Saves a summary of today's events for future context."""
    try:
        if os.path.exists(MEMORY_PATH):
            with open(MEMORY_PATH, 'r') as f:
                memory = json.load(f)
        else:
            memory = []
            
        memory.append({
            "date": str(datetime.date.today()),
            "summary": new_summary[:500] 
        })
        
        with open(MEMORY_PATH, 'w') as f:
            json.dump(memory[-7:], f, indent=2)
            
    except Exception as e:
        print(f"Error updating memory: {e}")

def send_to_discord(report):
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("\n--- [DISCORD WEBHOOK MISSING - PRINTING REPORT] ---\n")
        print(report)
        return
        
    chunks = [report[i:i + 1900] for i in range(0, len(report), 1900)]
    for chunk in chunks:
        requests.post(webhook_url, json={"content": chunk})

def main():
    print("Starting FPL Intelligence gathering (Deduplicated Mode)...")
    
    # 1. Load Sources & Memory
    with open(CONFIG_PATH, 'r') as f:
        sources_config = json.load(f)
    
    memory_context = ""
    if os.path.exists(MEMORY_PATH):
        try:
            with open(MEMORY_PATH, 'r') as f:
                mem_data = json.load(f)
                memory_context = "\n".join([f"{m['date']}: {m['summary']}" for m in mem_data])
        except:
            memory_context = "No history yet."
        
    # 2. Fetch Data (Internal Stats + News)
    stats = get_fpl_stats()
    news = gather_news_with_gemini(sources_config, memory_context)
    
    # 3. Reasoning (Gemini handles everything)
    reasoning = get_gemini_reasoning(news, stats, memory_context)
            
    # 4. Build Final Report
    header = f"🚀 **FPL Daily Intelligence Briefing - {datetime.date.today()}** 🚀\n"
    footer = "\n---\n*Disclaimer: Decisions are your own. Good luck!*"
    
    final_report = f"{header}\n### Latest FPL Intelligence (Gathered by Gemini):\n{news}\n\n### 🧠 Gemini Lead Strategist Analysis:\n{reasoning}{footer}"
    print(final_report)

    # 5. Update Memory & Send to Discord
    update_memory(news)
    # send_to_discord(final_report)
    print("Report completed successfully!")

if __name__ == "__main__":
    main()
