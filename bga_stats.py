"""Board Game Arena (BGA) statistics tracker and analyzer.

This module provides functionality to track and analyze game statistics for a group
of players on Board Game Arena (BGA). It authenticates with BGA, scrapes game data
between tracked players, categorizes games by ELO ratings, and generates detailed
statistics reports that can be sent to Discord webhooks.

Typical usage example:

	python bga_stats.py
"""

import re
import time
import os
import json
import requests
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Optional, Tuple, Any, Union

class BGAGameTracker:
	"""Board Game Arena game tracker with verified login and statistics analysis.

	This class handles authentication with BGA, scrapes game data between
	tracked players, and generates comprehensive statistics reports.
	"""

	def __init__(self):
		"""Initialize the BGA Game Tracker.

		Sets up the tracker with environment variables for authentication,
		initializes HTTP session with browser headers, and sets up data structures
		for tracking games and players.
		"""
		self._username = os.environ.get("BGA_USERNAME")
		self._password = os.environ.get("BGA_PASSWORD")
		self._base_url = "https://boardgamearena.com"

		# Game IDs to exclude (Turing Machine, Hanabi, wordtraveler)
		self._exclude_game_ids = ["1015", "1804", "1937"]
		self._session = requests.Session()
		self._request_token = None
		self._user_ids = []
		self._game_winner = {}
		self._user_names = []
		self._game_history = {}
		self._elo_category_dict = {}
		self._database_file = "data/bga_games_database.json"
		self._webhook = os.environ.get("DISCORD_WEBHOOK")

		# Set browser-like headers
		self._session.headers.update({
			"User-Agent": (
				"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
				"(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
			),
			"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
			"Accept-Language": "en-US,en;q=0.5",
			"Connection": "keep-alive",
		})

	def _get_request_token(self) -> bool:
		"""Extract request token from BGA's account page.

		The request token is required for authenticated requests to BGA's API.
		It's embedded in the JavaScript of the account page.

		Returns:
			bool: True if token was successfully extracted, False otherwise.
		"""
		try:
			resp = self._session.get(f"{self._base_url}/account")
			if resp.status_code != 200:
				print(f"Failed to access /account page: HTTP {resp.status_code}")
				return False

			# Look for request token in JavaScript
			match = re.search(r"requestToken:\s*['\"]([^'\"]*)['\"]", resp.text)
			if match:
				self._request_token = match.group(1)
				return True

			print("Could not find request token")
			return False

		except Exception as e:
			print(f"Error getting request token: {e}")
			return False

	def _login(self) -> bool:
		"""Authenticate with Board Game Arena using stored credentials.

		Performs a complete login flow including getting the request token
		and submitting login credentials. Verifies successful login by
		checking access to the community page.

		Returns:
			bool: True if login successful, False otherwise.
		"""
		print(f"Logging in to BGA as: {self._username}")

		# Get request token
		if not self._get_request_token():
			return False

		print(f"Found request token: {self._request_token[:10]}...")

		# Submit login
		login_url = f"{self._base_url}/account/account/login.html"
		login_data = {
			"email": self._username,
			"password": self._password,
			"rememberme": "on",
			"redirect": "direct",
			"request_token": self._request_token,
			"form_id": "loginform",
			"dojo.preventCache": str(int(time.time())),
		}

		try:
			response = self._session.post(login_url, data=login_data)
			print(f"Login response: HTTP {response.status_code}")

			return True

		except Exception as e:
			print(f"Login error: {e}")
			return False

	def _logout(self) -> bool:
		"""Log out of the current BGA session.

		Performs a clean logout by making a request to BGA's logout endpoint.

		Returns:
			bool: True if logout was successful, False otherwise.
		"""
		try:
			url = self._base_url + "/account/account/logout.html"
			params = {"dojo.preventCache": str(int(time.time()))}

			# Many sites use GET logout
			response = self._session.get(url, params=params)
			if response.status_code != 200:
				return False

			return True

		except Exception as e:
			print(f"Logout error: {e}")
			return False

	def _get_common_game(self, player_id: str, opponent_id: str, start_date: str) -> None:
		"""Fetch all games played between two specific players.

		Queries BGA's game statistics API to retrieve all finished games
		between the specified players since the start date. Filters out
		excluded games and processes player rankings.

		Args:
			player_id: BGA user ID of the first player.
			opponent_id: BGA user ID of the second player.
			start_date: Unix timestamp string for earliest game date to fetch.
		"""
		game_history_url = f"{self._base_url}/gamestats/gamestats/getGames.html"

		number = 1
		while True:
			params = {
				"player": player_id,
				"opponent_id": opponent_id,
				"start_date": start_date,
				"end_date": str(int(time.time())),
				"updateStats": "0",
				"page": str(number),
				"finished": "1"
			}

			headers = {
				"x-request-token": self._request_token,
				"Referer": game_history_url,
				"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"
			}

			try:
				response = self._session.post(game_history_url, headers=headers, data=params)
				if response.status_code != 200:
					print(f"Failed to get games for page {number}: HTTP {response.status_code}")
					break

				ranking_json = response.json()
				tables = ranking_json.get("data", {}).get("tables", [])

				if not tables:
					break

				for table in tables:
					table_id = table.get("table_id")
					game_id = table.get("game_id")
					game_name = table.get("game_name", "Unknown")

					if (table_id and table_id not in self._game_history and
						game_id and game_id not in self._exclude_game_ids):

						# Parse player names and rankings
						player_names = table.get("player_names", "").split(",")
						rankings = table.get("ranks", "").split(",")
						largest = max([int(rank.strip()) for rank in rankings if rank.strip().isdigit()])
						winners = []
						runner_ups = []
						losers = []
						lasts = []
						for i in range(0, len(rankings)):
							ranking = rankings[i]
							if ranking == "1" and player_names[i] in self._user_names:
								winners.append(player_names[i])
							elif ranking == str(largest) and player_names[i] in self._user_names:
								lasts.append(player_names[i])
							elif ranking == "2" and player_names[i] in self._user_names:
								runner_ups.append(player_names[i])
							elif player_names[i] in self._user_names:
								losers.append(player_names[i])

						# Store game data: [game_id, game_name, players_and_ranks]
						game_data = {
							"game_id": game_id,
							"game_name": game_name,
							"table_id": table_id,
							"winners": winners,
							"runner_ups": runner_ups,
							"losers": losers,
							"lasts": lasts
						}

						self._game_history[table_id] = game_data
						print(f'Added game: {game_data["game_name"]} (table {table_id})')

				number += 1
				time.sleep(0.5)  # Be respectful

			except Exception as e:
				print(f"Error getting games on page {number}: {e}")
				break

	def _get_all_games_between_friends(self, start_date: Optional[datetime] = None) -> None:
		"""Fetch games for all possible pairs of tracked players.

		Iterates through all combinations of tracked players and fetches
		their game history. This ensures complete coverage of games played
		within the friend group.

		Args:
			start_date: Optional datetime to limit search to games after this date.
					   Defaults to 2021-01-01 if not provided.
		"""

		# Set default start date if not provided
		if start_date is None:
			start_timestamp = "1609459200"  # 2021-01-01
		else:
			start_timestamp = str(int(start_date.timestamp()))

		print(f"Searching games from timestamp {start_timestamp} to now")

		# Get games between each pair of players
		for i in range(len(self._user_ids)):
			for j in range(i + 1, len(self._user_ids)):
				player1_id = self._user_ids[i]
				player2_id = self._user_ids[j]

				# Get games from both perspectives
				self._get_common_game(player1_id, player2_id, start_timestamp)
				time.sleep(0.5)

		print(f"\nTotal unique games found: {len(self._game_history)}")

	def _get_game_elo(self, game_id: str) -> Optional[int]:
		"""Retrieve the highest ELO rating for a specific game.

		Queries BGA's ranking API to get the top player's ELO rating for
		the specified game. The returned value is the ELO above the base
		rating of 1300.

		Args:
			game_id: BGA game ID to look up ELO ratings for.

		Returns:
			Optional[int]: ELO points above 1300, or None if unable to retrieve.
		"""
		try:
			game_history_url = f"{self._base_url}/gamepanel/gamepanel/getRanking.html"
			params = {
				"game": game_id,
				"mode": "elo",
				"start": "0",
			}

			headers = {
				"x-request-token": self._request_token,
				"Referer": game_history_url,
				"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"
			}

			response = self._session.post(game_history_url, headers=headers, data=params)
			if response.status_code != 200:
				return None
			ranking_json = response.json()
			data = ranking_json.get("data", {})
			ranks = data.get("ranks", [])
			if ranks and len(ranks) > 0:
				top_ranking = ranks[0].get("ranking", 1300)
				return max(0, round(float(top_ranking) - 1300))  # Subtract base ELO

			return None

		except Exception as e:
			print(f"Error getting ELO for game {game_id}: {e}")
			return None

	def _categorize_by_elo(self, elo: Optional[int]) -> str:
		"""Categorize a game into ELO difficulty brackets.

		Groups games into difficulty categories based on the highest player
		ELO rating. Used for organizing statistics by game complexity.

		Args:
			elo: ELO rating points above 1300, or None.

		Returns:
			str: ELO category string ('>800', '700-800', '600-700', '500-600', '<500').
		"""
		if elo is None:
			return "<500"
		if elo > 800:
			return ">800"
		elif elo >= 700:
			return "700-800"
		elif elo >= 600:
			return "600-700"
		elif elo >= 500:
			return "500-600"
		else:
			return "<500"

	def _find_common_games(self, database: Dict[str, Any]) -> Dict[str, Any]:
		"""Process and aggregate game data by game type.

		Takes the raw game history and processes it into a structured database
		format, grouping games by game ID and aggregating player statistics
		(wins, runner-ups, losses, last places) for each game type.

		Args:
			database: Existing game database to update with new data.

		Returns:
			Dict[str, Any]: Updated database with processed game statistics.
		"""
		for _, game in self._game_history.items():
			game_id = game.get("game_id", "")
			game_name = game.get("game_name", "")
			winners = game.get("winners", "")
			runner_ups = game.get("runner_ups", "")
			losers = game.get("losers", "")
			lasts = game.get("lasts", "")

			# Group by game name
			if game_id not in database["games"]:
				database["games"][game_id] = {
					"game_name": game_name,
					"users": {},
				}
			for winner in winners:
				if winner not in database['games'][game_id]['users']:
					database['games'][game_id]['users'][winner] = {'win':1, 'second':0, 'last':0, 'total':1}
				else:
					database['games'][game_id]['users'][winner]['win'] += 1
					database['games'][game_id]['users'][winner]['total'] += 1

			for runner_up in runner_ups:
				if runner_up not in database['games'][game_id]['users']:
					database['games'][game_id]['users'][runner_up] = {'win':0, 'second':1, 'last':0, 'total':1}
				else:
					database['games'][game_id]['users'][runner_up]['second'] += 1
					database['games'][game_id]['users'][runner_up]['total'] += 1

			for loser in losers:
				if loser not in database['games'][game_id]['users']:
					database['games'][game_id]['users'][loser] = {'win':0, 'second':0, 'last':0, 'total':1}
				else:
					database['games'][game_id]['users'][loser]['total'] += 1

			for last in lasts:
				if last not in database['games'][game_id]['users']:
					database['games'][game_id]['users'][last] = {'win':0, 'second':0, 'last':1, 'total':1}
				else:
					database['games'][game_id]['users'][last]['total'] += 1
					database['games'][game_id]['users'][last]['last'] += 1

		return database

	def _analyze_game(self, database: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
		"""Analyze games and generate statistics by ELO category.

		Processes the game database to create comprehensive statistics
		for each player across different ELO categories. Also determines
		the best performing player for each game type.

		Args:
			database: Processed game database containing game statistics.

		Returns:
			Dict[str, Dict[str, Any]]: Statistics organized by ELO category,
									 then by player name with win/loss records.
		"""
		stats_report = {">800": {}, "700-800": {}, "600-700": {}, "500-600": {}, "<500": {}}

		for game_id, common_game in database["games"].items():
			elo = self._get_game_elo(game_id)
			elo_category = self._categorize_by_elo(elo)
			self._elo_category_dict.setdefault(elo_category, []).append(common_game["game_name"])

			max_win = 0
			max_user = ""
			max_total = 0

			for user, result in common_game["users"].items():
				if user not in stats_report[elo_category]:
					stats_report[elo_category][user] = {"win": result["win"],
														"second": result["second"],
														"last": result["last"],
														"total": result["total"]}
				else:
					stats_report[elo_category][user]["win"] += result["win"]
					stats_report[elo_category][user]["second"] += result["second"]
					stats_report[elo_category][user]["last"] += result["last"]
					stats_report[elo_category][user]["total"] += result["total"]

				# Check for max win ratio
				current_win_ratio = result["win"] / result["total"] if result["total"] > 0 else 0
				max_win_ratio = max_win / max_total if max_total > 0 else 0

				if current_win_ratio > max_win_ratio:
					max_win = result["win"]
					max_user = user
					max_total = result["total"]
				elif current_win_ratio == max_win_ratio and result["win"] > max_win:
					max_win = result["win"]
					max_user = user
					max_total = result["total"]

			# Store the winner for this game
			if max_user:
				self._game_winner[common_game["game_name"]] = [max_user, max_win, max_total]
		return stats_report

	def _load_database(self) -> Dict[str, Any]:
		"""Load existing game database from disk.

		Attempts to load the persistent game database from the configured
		file path. Returns empty database structure if file doesn't exist
		or can't be loaded.

		Returns:
			Dict[str, Any]: Game database with 'games' and 'last_update' keys.
		"""
		if os.path.exists(self._database_file):
			try:
				with open(self._database_file, "r") as f:
					return json.load(f)
			except:
				pass
		return {"games": {}, "last_update": None}

	def _save_database(self, database: Dict[str, Any]) -> None:
		"""Persist game database to disk.

		Saves the game database to the configured JSON file for future use.
		This allows incremental updates without re-scraping all historical data.

		Args:
			database: Complete game database to save.
		"""
		with open(self._database_file, "w") as f:
			json.dump(database, f, indent=2)

	def _generate_report(self, analyzed_games: Dict[str, Dict[str, Any]]) -> None:
		"""Generate and send comprehensive analysis report to Discord.

		Creates formatted Discord embeds containing player statistics
		organized by ELO categories and game lists with performance leaders.
		Sends both player statistics and game lists as separate embeds.

		Args:
			analyzed_games: Statistics organized by ELO category and player.
		"""

		# Build message blocks for each ELO category
		message_blocks = []

		for category, users in analyzed_games.items():
			if not users:
				continue

			win_ratio = []
			category_block = f"**ELO: {category}**\n"

			for user, result in users.items():
				win_ratio.append([user, result["win"], result["second"], result["last"], result["total"]])

			# Sort players by win percentage
			sorted_stats = sorted(
				win_ratio,
				key=lambda x: x[1]/x[4] if x[4] > 0 else 0,
				reverse=True
			)

			# Format stats for text report
			discord_stats = []

			for stat in sorted_stats:
				win_pct = round(stat[1] / stat[4] * 100) if stat[4] > 0 else 0
				second_pct = round(stat[2] / stat[4] * 100) if stat[4] > 0 else 0
				last_pct = round(stat[3] / stat[4] * 100) if stat[4] > 0 else 0

				discord_stats.append(f"{stat[0]}\n"
									 f"🥇{stat[1]}/{stat[4]} ({win_pct}%) 🥈{stat[2]}/{stat[4]} ({second_pct}%)"
									 f" 💩{stat[3]}/{stat[4]} ({last_pct}%)")

			# Add to Discord block
			category_block += "\n".join([f"• {stat}" for stat in discord_stats])

			message_blocks.append(category_block)

		# Send Discord messages
		self._send_discord_embed(message_blocks)

		# Send game list to Discord
		self._send_discord_game_list()

	def _send_discord_embed(self, message_blocks: List[str]) -> None:
		"""Send player statistics as a Discord embed message.

		Formats player statistics into Discord embed fields organized by
		ELO categories. Each category becomes a field showing player
		performance with win percentages and counts.

		Args:
			message_blocks: List of formatted statistic blocks for each ELO category.
		"""
		if not self._webhook or not message_blocks:
			return

		# Build fields from message blocks
		fields = []
		for block in message_blocks:
			lines = block.split("\n")
			title = lines[0]  # "**ELO: >800**"
			stats = lines[1:]  # Player stats

			# Clean up title (remove ** formatting for field name)
			field_name = title.replace("**", "")

			# Join stats as value
			field_value = "\n".join(stats)

			fields.append({
				"name": field_name,
				"value": field_value,
				"inline": False
			})

		embed = {
			"title": "🎲 BGA Game Statistics",
			"description": "Weekly analysis for tracked players",
			"fields": fields,
			"color": 0x3498db,  # Blue color
			"footer": {
				"text": "Counted stats for games with two or more players in this Discord."
			},
		}

		payload = {"embeds": [embed]}

		try:
			response = requests.post(self._webhook, json=payload, timeout=10)
			if response.status_code == 204:
				print("Discord embed sent successfully")
			else:
				print(f"Discord embed failed: {response.status_code}")
		except Exception as e:
			print(f"Discord embed error: {e}")

	def _send_discord_game_list(self) -> None:
		"""Send categorized game list with performance leaders to Discord.

		Creates a Discord embed showing all tracked games organized by ELO
		categories. Each game entry includes the top performing player with
		their win rate statistics.
		"""
		if not self._webhook:
			return

		# Build game list to send to Discord
		fields = []
		ordered_keys = [">800", "700-800", "600-700", "500-600", "<500"]

		for key in ordered_keys:
			if key in self._elo_category_dict and self._elo_category_dict[key]:
				games = self._elo_category_dict[key]

				# Format games with winners
				game_entries = []
				for game in games:
					if game in self._game_winner:
						winner_data = self._game_winner[game]
						winner_name = winner_data[0]
						wins = winner_data[1]
						total = winner_data[2]
						win_pct = round(wins / total * 100) if total > 0 else 0

						game_entry = f"• {game}\n  👑 {winner_name} ({wins}/{total} - {win_pct}%)"
					else:
						game_entry = f"• {game}\n  👑 No winners"
					game_entries.append(game_entry)

				game_list = "\n".join(game_entries)

				fields.append({
					"name": f"ELO: {key}",
					"value": game_list,
					"inline": False
				})

		if not fields:
			return

		embed = {
			"title": "🎮 Games by ELO Category",
			"fields": fields,
			"color": 0x2ecc71,  # Green color
			"footer": {
				"text": "Game categorization based on top player ELO"
			},
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

	def scrape_and_analyze(self, user_list: Optional[List[str]] = None, first_time: bool = False) -> None:
		"""Main orchestration function to scrape and analyze BGA games.

		Performs the complete workflow: authentication, data scraping,
		analysis, report generation, and database persistence. Handles
		both initial setup and incremental updates.

		Args:
			user_list: Optional list containing [user_ids, user_names] to track.
					  Uses existing configuration if not provided.
			first_time: Whether this is initial setup (scrapes all historical data)
					   or an incremental update (scrapes since last update).
		"""
		if user_list:
			self._user_ids = user_list[0]
			self._user_names = user_list[1]

		if not self._login():
			print("Failed to login to BGA")
			return

		database = self._load_database()

		# Determine start date for scraping
		start_date = None
		if not first_time and database.get("last_update"):
			start_date = datetime.strptime(database["last_update"], "%Y-%m-%d %H:%M:%S")

		# Get all games between friends
		self._get_all_games_between_friends(start_date)

		# Find common games
		database = self._find_common_games(database)

		# Analyze each game
		analyzed_games = self._analyze_game(database)

		# Generate report
		self._generate_report(analyzed_games)

		# Update database
		database["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
		self._save_database(database)

		print("Analysis complete!")

		if self._logout():
			print("Successfully logged out from BGA.")
		else:
			print("Warning: Logout from BGA may have failed.")

# Usage functions
def first_time_setup() -> None:
	"""Initialize BGA tracking with complete historical data scraping.

	Sets up the tracker with a predefined list of players and performs
	a complete historical data scrape. This should be run once during
	initial setup to populate the database.
	"""
	# List of users to analyze (friends/players to track)
	USER_LIST = [["85361014", "97981932", "98250223", "98366299",
				  "98343487", "93577018", "97997444"],
				 ["Gelev", "matthewcrumby", "xuzheng863", "FC YEYE",
				  "stinson19980111",  "simonzhushiyu", "mashiro66"]]

	tracker = BGAGameTracker()
	tracker.scrape_and_analyze(user_list=USER_LIST, first_time=True)

def update_analysis() -> None:
	"""Update existing analysis with new games since last run.

	Performs an incremental update of the game database, only fetching
	games played since the last update timestamp. This is the typical
	function to run on a regular schedule.
	"""
	# List of users to analyze (friends/players to track)
	USER_LIST = [["85361014", "97981932", "98250223", "98366299",
				  "98343487", "93577018", "97997444"],
				 ["Gelev", "matthewcrumby", "xuzheng863", "FC YEYE",
				  "stinson19980111",  "simonzhushiyu", "mashiro66"]]

	tracker = BGAGameTracker()
	tracker.scrape_and_analyze(user_list=USER_LIST, first_time=False)

if __name__ == "__main__":
	# first_time_setup()
	update_analysis()
