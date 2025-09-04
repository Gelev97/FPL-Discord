'''BGA Game Tracker - Complete implementation with verified login and game analysis.'''

import re
import time
import os
import json
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Optional, Tuple, Any, Union
import requests

class BGAGameTracker:
    '''Board Game Arena game tracker with verified login.'''
    
    def __init__(self):
        '''Initialize the BGA Game Tracker.'''
        self._username = os.environ.get("BGA_USERNAME")
        self._password = os.environ.get("BGA_PASSWORD")
        self._base_url = 'https://boardgamearena.com'
        self._exclude_game_ids = ['1015', '1804']  # Game IDs to exclude (Turing Machine, Hanabi)
        self._session = requests.Session()
        self._request_token: Optional[str] = None
        self._user_ids: List[str] = []
        self._user_names: List[str] = []
        self._game_history: Dict[str, Dict] = {}
        self._elo_category_dict: Dict[int, List] = {}
        self._database_file: str = 'data/bga_games_database.json'
        self._webhook: Optional[str] = os.environ.get("DISCORD_WEBHOOK")
        
        # Set browser-like headers
        self._session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
        })
    
    def _get_request_token(self) -> bool:
        '''Get the request token from BGA's account page.'''
        try:
            resp = self._session.get(f'{self._base_url}/account')
            if resp.status_code != 200:
                print(f'Failed to access /account page: HTTP {resp.status_code}')
                return False
            
            # Look for request token in JavaScript
            match = re.search(r"requestToken:\s*['\"]([^'\"]*)['\"]", resp.text)
            if match:
                self._request_token = match.group(1)
                return True

            print('Could not find request token')
            return False
            
        except Exception as e:
            print(f'Error getting request token: {e}')
            return False
    
    def _login(self) -> bool:
        '''Login to BGA with stored credentials.'''
        print(f'Logging in to BGA as: {self._username}')
        
        # Get request token
        if not self._get_request_token():
            return False
        
        print(f'Found request token: {self._request_token[:10]}...')
        
        # Submit login
        login_url = f'{self._base_url}/account/account/login.html'
        login_data = {
            'email': self._username,
            'password': self._password,
            'rememberme': 'on',
            'redirect': 'direct',
            'request_token': self._request_token,
            'form_id': 'loginform',
            'dojo.preventCache': str(int(time.time())),
        }
        
        try:
            response = self._session.post(login_url, data=login_data)
            print(f'Login response: HTTP {response.status_code}')
            
            # Verify login
            community_resp = self._session.get(f'{self._base_url}/community')
            success = (community_resp.status_code == 200 and 
                      'You must be logged in to see this page.' not in community_resp.text)

            if success:
                print('Login successful!')
            else:
                print('Login failed!')
            
            return success
            
        except Exception as e:
            print(f'Login error: {e}')
            return False

    def _get_common_game(self, player_id: str, opponent_id: str, start_date: str) -> None:
        '''Get common games between two players.'''
        game_history_url = f'{self._base_url}/gamestats/gamestats/getGames.html'
        
        number = 1
        while True:
            params = {
                'player': player_id,
                'opponent_id': opponent_id,
                'start_date': start_date,
                'end_date': str(int(time.time())),
                'updateStats': '0',
                'page': str(number),
                'finished': '1'
            }
        
            headers = {
                'x-request-token': self._request_token,
                'Referer': game_history_url,
                'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'
            }
            
            try:
                response = self._session.post(game_history_url, headers=headers, data=params)
                if response.status_code != 200:
                    print(f'Failed to get games for page {number}: HTTP {response.status_code}')
                    break
                    
                ranking_json = response.json()
                tables = ranking_json.get('data', {}).get('tables', [])
                
                if not tables:
                    break
                
                for table in tables:
                    table_id = table.get('table_id')
                    game_id = table.get('game_id')
                    game_name = table.get('game_name', 'Unknown')
                    
                    if (table_id and table_id not in self._game_history and 
                        game_id and game_id not in self._exclude_game_ids):
                        
                        # Parse player names and rankings
                        player_names = table.get('player_names', '').split(',')
                        rankings = table.get('ranks', '').split(',')
                        winners = []
                        runner_ups = []
                        losers = []
                        for i in range(0, len(rankings)):
                            ranking = rankings[i]
                            if ranking == '1' and player_names[i] in self._user_names:
                                winners.append(player_names[i])
                            elif ranking == '2' and player_names[i] in self._user_names:
                                runner_ups.append(player_names[i])
                            elif player_names[i] in self._user_names:
                                losers.append(player_names[i])
                        
                        # Store game data: [game_id, game_name, players_and_ranks]
                        game_data = {
                            'game_id': game_id,
                            'game_name': game_name,
                            'table_id': table_id,
                            'winners': winners,
                            'runner_ups': runner_ups,
                            'losers': losers
                        }
            
                        self._game_history[table_id] = game_data
                        print(f"Added game: {game_data['game_name']} (table {table_id})")
                
                number += 1
                time.sleep(0.5)  # Be respectful
                
            except Exception as e:
                print(f'Error getting games on page {number}: {e}')
                break

    def _get_all_games_between_friends(self, start_date: Optional[datetime] = None) -> None:
        '''Get all games between all combinations of friends.'''
        
        # Set default start date if not provided
        if start_date is None:
            start_timestamp = '1609459200'  # 2021-01-01
        else:
            start_timestamp = str(int(start_date.timestamp()))
        
        print(f'Searching games from timestamp {start_timestamp} to now')
         
        # Get games between each pair of players
        for i in range(len(self._user_ids)):
            for j in range(i + 1, len(self._user_ids)):
                player1_id = self._user_ids[i]
                player2_id = self._user_ids[j]
                
                # Get games from both perspectives
                self._get_common_game(player1_id, player2_id, start_timestamp)
                time.sleep(0.5)

        print(f'\nTotal unique games found: {len(self._game_history)}')

    def _get_game_elo(self, game_id: str) -> int:
        '''Get highest ELO for a game.'''
        try:
            game_history_url = f'{self._base_url}/gamepanel/gamepanel/getRanking.html'
            params = {
                'game': game_id,
                'mode': 'elo',
                'start': '0',
            }

            headers = {
                'x-request-token': self._request_token,
                'Referer': game_history_url,
                'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'
            }

            response = self._session.post(game_history_url, headers=headers, data=params)
            if response.status_code != 200:
                return None
            ranking_json = response.json()
            data = ranking_json.get('data', {})
            ranks = data.get('ranks', [])
            if ranks and len(ranks) > 0:
                top_ranking = ranks[0].get('ranking', 1300)
                return max(0, round(float(top_ranking) - 1300))  # Subtract base ELO
            
            return None
            
        except Exception as e:
            print(f'Error getting ELO for game {game_id}: {e}')
            return None
    
    def _categorize_by_elo(self, elo: int) -> str:
        '''Categorize games by ELO ranges.'''
        if elo > 800:
            return '>800'
        elif elo >= 700:
            return '700-800'
        elif elo >= 600:
            return '600-700'
        elif elo >= 500:
            return '500-600'
        else:
            return '<500'
    
    def _find_common_games(self, database: Dict[str, Any]) -> Dict[str, Any]:
        '''Process games and group by game name.'''        
        for _, game in self._game_history.items():
            game_id = game.get('game_id', '')
            game_name = game.get('game_name', '')
            winners = game.get('winners', '')
            runner_ups = game.get('runner_ups', '')
            losers = game.get('losers', '')

            # Group by game name
            if game_id not in database['games']:
                database['games'][game_id] = {
                    'game_name': game_name,                
                    'users': {},
                }
            for winner in winners:
                if winner not in database['games'][game_id]['users']:
                    database['games'][game_id]['users'][winner] = {'win':1, 'second':0, 'total':1}
                else:
                    database['games'][game_id]['users'][winner]['win'] += 1
                    database['games'][game_id]['users'][winner]['total'] += 1
            
            for runner_up in runner_ups:
                if runner_up not in database['games'][game_id]['users']:
                    database['games'][game_id]['users'][runner_up] = {'win':0, 'second':1, 'total':1}
                else:
                    database['games'][game_id]['users'][runner_up]['second'] += 1
                    database['games'][game_id]['users'][runner_up]['total'] += 1
            
            for loser in losers:
                if loser not in database['games'][game_id]['users']:
                    database['games'][game_id]['users'][loser] = {'win':0, 'second':0, 'total':1}
                else:
                    database['games'][game_id]['users'][loser]['total'] += 1

        return database

    def _analyze_game(self, database: Dict[str, Any]) -> None:
        stats_report = {">800": {}, "700-800": {}, "600-700": {}, "500-600": {}, "<500": {}}
        for game_id, common_game in database['games'].items():
            elo = self._get_game_elo(game_id)
            elo_category = self._categorize_by_elo(elo)
            self._elo_category_dict.setdefault(elo_category, []).append(common_game['game_name'])
            for user, result in common_game['users'].items():
                if user not in stats_report[elo_category]:
                    stats_report[elo_category][user] = {'win': result['win'],
                                                        'second': result['second'],
                                                        'total': result['total']}
                else:
                    stats_report[elo_category][user]['win'] += result['win']
                    stats_report[elo_category][user]['second'] += result['second']
                    stats_report[elo_category][user]['total'] += result['total']

        return stats_report

    def _load_database(self) -> Dict[str, Any]:
        '''Load existing game database.'''
        if os.path.exists(self._database_file):
            try:
                with open(self._database_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {'games': {}, 'last_update': None}
    
    def _save_database(self, database: Dict[str, Any]) -> None:
        '''Save game database.'''
        with open(self._database_file, 'w') as f:
            json.dump(database, f, indent=2)
    
    def _send_discord_embed(self, elo_categories: Dict[str, List[Tuple[str, Dict[str, Any]]]], category_totals: Dict[str, Dict[str, Any]]) -> None:
        """Send BGA stats as Discord embed with one ELO category per field row."""
        if not self._webhook:
            return
        
        # Create fields - one per ELO category
        fields = []
        ordered_keys = [">800", "700-800", "600-700", "500-600", "<500"]
        
        for category in ordered_keys:
            if category not in elo_categories or not elo_categories[category]:
                continue
                
            # Get category totals
            if category in category_totals:
                totals = category_totals[category]['player_stats']
                
                # Sort players by win percentage
                sorted_players = sorted(
                    totals.items(),
                    key=lambda x: x[1]['win_percentage'],
                    reverse=True
                )
                
                # Create compact value for this category
                value_lines = []
                for player, stats in sorted_players:
                    line = f"{player}: 1st {stats['win_ratio']} ({stats['win_percentage']}%) | 2nd {stats['second_ratio']} ({stats['second_percentage']}%)"
                    value_lines.append(line)
                
                # Join with newlines and check length
                value = "\n".join(value_lines)
                if len(value) > 1024:  # Discord field limit
                    # Truncate to fit
                    value = value[:1000] + "...\n*(truncated)*"
                
                fields.append({
                    "name": f"ELO: {category}",
                    "value": value,
                    "inline": False  # Full width for readability
                })
        
        # Create main embed
        embed = {
            "title": "BGA Game Statistics",
            "description": f"Analysis for: {', '.join(self.user_list)}",
            "color": 0x3498db,  # Blue
            "fields": fields,
            "footer": {
                "text": "Counted stats for games with two or more players in this Discord."
            },
        }
        
        payload = {"embeds": [embed]}
        
        try:
            response = requests.post(self._webhook, json=payload, timeout=10)
            if response.status_code == 204:
                print("Discord stats embed sent successfully")
            else:
                print(f"Discord stats embed failed: {response.status_code}")
        except Exception as e:
            print(f"Discord stats embed error: {e}")

    def _send_discord_game_list(self, elo_categories: Dict[str, List[Tuple[str, Dict[str, Any]]]]) -> None:
        """Send game list as a separate compact Discord embed."""
        if not self._webhook:
            return
        
        # Create one field per ELO category with game names
        fields = []
        ordered_keys = [">800", "700-800", "600-700", "500-600", "<500"]
        
        for category in ordered_keys:
            if category not in elo_categories or not elo_categories[category]:
                continue
                
            # Get game names for this category
            game_names = [game_name for game_name, _ in elo_categories[category]]
            
            # Format as comma-separated list
            games_text = ", ".join(game_names)
            
            # Check Discord field limit
            if len(games_text) > 1024:
                games_text = games_text[:1000] + "..."
            
            fields.append({
                "name": f"{category} ELO",
                "value": games_text,
                "inline": False
            })
        
        # Create game list embed
        embed = {
            "title": "Games by ELO Category",
            "description": "Complete list of analyzed games",
            "color": 0x2ecc71,  # Green
            "fields": fields,
            "footer": {
                "text": "Game categorization based on top player ELO"
            }
        }
    
    payload = {"embeds": [embed]}
    
    try:
        response = requests.post(self._webhook, json=payload, timeout=10)
        if response.status_code == 204:
            print("Discord game list sent successfully")
        else:
            print(f"Discord game list failed: {response.status_code}")
    except Exception as e:
        print(f"Discord game list error: {e}")

    def _generate_report(self, analyzed_games: Dict[str, Dict[str, Any]]) -> None:
        """Generate and save the analysis report with Discord integration."""
        report = []
        
        # Calculate category totals first
        category_totals = self.calculate_category_totals(analyzed_games)
        
        # Generate text report
        ordered_keys = [">800", "700-800", "600-700", "500-600", "<500"]
        
        for category in ordered_keys:
            if category not in category_totals:
                continue
                
            report.append(f'ELO CATEGORY: {category}')
            report.append('-' * 40)
            
            # Show category totals
            totals = category_totals[category]['player_stats']
            sorted_stats = sorted(
                totals.items(),
                key=lambda x: x[1]['win_percentage'],
                reverse=True
            )
            
            for player, stats in sorted_stats:
                report.append(
                    f'  {player}: '
                    f'1st {stats["win_ratio"]} ({stats["win_percentage"]}%), '
                    f'2nd {stats["second_ratio"]} ({stats["second_percentage"]}%)'
                )
            
            report.append('')

        # Send to Discord with embeds
        self._send_discord_embed(analyzed_games, category_totals)
        
        # Send game list
        self._send_discord_game_list(analyzed_games)
        
        # Save text report
        with open('bga_analysis_report.txt', 'w') as f:
            f.write('\n'.join(report))
        
        print("Reports generated and sent to Discord")


    def scrape_and_analyze(self, user_list: Optional[List[str]] = None, first_time: bool = False) -> None:
        '''Main function to scrape and analyze games.'''
        if user_list:
            self._user_ids = user_list[0]
            self._user_names = user_list[1]
        
        if not self._login():
            print('Failed to login to BGA')
            return
        
        database = self._load_database()
        
        # Determine start date for scraping
        start_date = None
        if not first_time and database.get('last_update'):
            start_date = datetime.strptime(database['last_update'], '%Y-%m-%d %H:%M:%S')
        
        # Get all games between friends
        self._get_all_games_between_friends(start_date)
        
        # Find common games
        database = self._find_common_games(database)
        
        # Analyze each game
        analyzed_games = self._analyze_game(database)
       
        # Generate report
        self._generate_report(analyzed_games)
        
        # Update database
        database['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self._save_database(database)
        
        print('Analysis complete!')

# Usage functions
def first_time_setup() -> None:
    '''Function to run the script for the first time.'''
    # List of users to analyze (friends/players to track)
    USER_LIST = [['85361014', '97981932', '98250223', '98366299', '98343487', '93577018', '97997444'], 
                 ['Gelev', 'matthewcrumby', 'xuzheng863', 'FC YEYE', 'stinson19980111',  'simonzhushiyu', 'mashiro66']]
    
    tracker = BGAGameTracker()
    tracker.scrape_and_analyze(user_list=USER_LIST, first_time=True)

def update_analysis() -> None:
    '''Function to update the analysis with new games.'''
    # List of users to analyze (friends/players to track)
    USER_LIST = [['85361014', '97981932', '98250223', '98366299', '98343487', '93577018', '97997444'], 
                 ['Gelev', 'matthewcrumby', 'xuzheng863', 'FC YEYE', 'stinson19980111',  'simonzhushiyu', 'mashiro66']]

    
    tracker = BGAGameTracker()
    tracker.scrape_and_analyze(user_list=USER_LIST, first_time=False)

if __name__ == '__main__':
   update_analysis()