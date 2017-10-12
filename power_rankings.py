# -*- coding: utf-8 -*-
# @Author: Charles Starr
# @Date:   2017-09-23 16:30:04
# @Last Modified by:   Charles Starr
# @Last Modified time: 2017-10-12 17:04:34

from lxml import html
from lxml import etree
import requests
import string
import numpy as np
import random
import copy
import csv
import pandas as pd
import constants
import sets

class Owner(object):
    # create an owner class for every owner in the standings table

    def __init__(self, name_complex, ID, year, league_id, wins, losses, rank):
        # initialize variables that will be needed for simulation
        self.name_complex = name_complex
        self.ID = ID
        self.year = year
        self.league_id = league_id
        self.wins = wins
        self.losses = losses
        self.games_played = self.wins + self.losses
        self.current_rank = rank
        self.scores = []
        self.final_opponents = self.schedule_data()
        self.win_percentage = self.calc_win_percentage()
        self.total_points = np.sum(self.scores)
        self.roster = self.populate_roster()
        self.lineup_scores = []
        self.lineup_deviations = []
        self.simulated_totals = []
        self.simulated_wins = []
        self.simulated_losses = []

    def schedule_data(self):
        # get info about games played and games remaining
        schedule_url = ('http://games.espn.go.com/ffl/schedule?leagueId='
            + self.league_id + '&teamId=' + self.ID + '&seasonId=' + self.year
            )
        raw_schedule = requests.get(schedule_url)
        html_schedule = html.fromstring(raw_schedule.text)
        opponents = []

        for index, score in enumerate(html_schedule.xpath('//nobr/a/text()'), 0):
            if not 'Box' in score:
                score = float(score[string.find(score, ' ')
                    + 1:string.find(score, '-')]
                    )
                self.scores.append(score)
            else:
                opponents.append(html_schedule.xpath(
                    '//a[@target="_top"]/@title')[index]
                )

        return opponents

    def calc_win_percentage(self):

        self.win_percentage = float(self.wins) / len(self.scores)

    def populate_roster(self):

    	roster_url = ('http://games.espn.com/ffl/clubhouse?leagueId=' +
    		self.league_id + '&teamId=' + self.ID + '&seasonId=' + self.year
    		)
    	raw_roster = requests.get(roster_url)
    	html_roster = html.fromstring(raw_roster.text)
    	roster = []

    	for player_row in html_roster.xpath('//tr[contains(@class, "pncPlayerRow")]'):
    		if player_row.xpath('./td[1]/text()')[0] != 'IR':
    			try:
    				player_name = player_row.xpath('./td[2]/a/text()')[0]
	    			position_raw = player_row.xpath('./td[2]/text()')[0]
	    			position = position_raw[position_raw.find(u'\xa0') + 1:].strip(u'\xa0')
	    			roster.append(Player(player_name, position))
	    		except:
	    			continue

    	return roster

    def set_lineups(self, league):

    	for week in range(0, 17, 1):
    		positions = ['QB', 'RB', 'RB', 'WR', 'WR', 'TE', 'FLEX', 'K', 'D/ST']
    		weekly_scores = []
    		weekly_deviations = []
    		
    		self.roster.sort(key = lambda player: player.projected_scores[week], reverse = True)
    		for player in self.roster:
    			if player.position in positions:
    				weekly_scores.append(player.projected_scores[week])
    				weekly_deviations.append(player.scoring_stdev)
    				positions.remove(player.position)
    			elif 'FLEX' in positions and player.position in ['RB', 'WR', 'TE']:
    				weekly_scores.append(player.projected_scores[week])
    				weekly_deviations.append(player.scoring_stdev)
    				positions.remove('FLEX')
    			else:
    				continue

    		for position in positions:
    			weekly_scores.append(league.positional_scores[position])
    			weekly_deviations.append(league.positional_deviations[position])
    		
    		self.lineup_scores.append(weekly_scores)
    		self.lineup_deviations.append(weekly_deviations)

    def __cmp__(self, other):

        if self.win_percentage > other.win_percentage:
            return 1
        elif self.win_percentage < other.win_percentage:
            return -1
        elif self.total_points > other.total_points:
            return 1
        elif self.total_points < other.total_points:
            return -1
        else:
            return 0

    def __str__(self):

        return self.name_complex

class SimulationOwner(Owner):
    #a copy of each owner is created for each simulation
    
    def __init__(self, owner): #passing owners from ownerlist for temporary sim class

        self.owner = owner
        self.name_complex = owner.name_complex
        self.wins = owner.wins
        self.losses = owner.losses
        self.games_played = owner.games_played      
        self.scores = copy.deepcopy(owner.scores)
        self.total_points = owner.total_points
        self.final_opponents = owner.final_opponents
        self.lineup_scores = np.array(owner.lineup_scores)
        self.lineup_deviations = np.array(owner.lineup_deviations)
        self.simulated_points = self.simulate_point_total() #simulated point total
        self.final_rank = 0
    
    def simulate_point_total(self):

        simulated_points = []
        for game in range(self.games_played, 13, 1):
        	scores = self.lineup_scores[game]
        	deviations = self.lineup_deviations[game]
    		game_score = 0.0
    		
    		for score, deviation in np.nditer([scores, deviations]):
    			player_score = (random.gauss(score, deviation))
    			if player_score < 0.0:
    				player_score = 0.0
    			game_score += player_score
           
           	simulated_points.append(game_score)
        
        self.total_points += sum(simulated_points)
        self.scores.extend(simulated_points)
        self.owner.simulated_totals.append(self.total_points)

        return simulated_points


class Player(object):

	def __init__(self, player_name, position):

		self.player_name = player_name
		self.name_trim()
		self.position = position
		self.game_scores = []
		self.full_team = None
		self.abbr_team = None
		self.scoring_average = 0.0
		self.scoring_stdev = 0.0
		self.schedule = []
		self.projected_scores = []

	def name_trim(self):

		if 'Jr.' in self.player_name or 'Sr.' in self.player_name:
			self.player_name = self.player_name[:-4]

		if self.player_name[-1] == 'V':
			self.player_name = self.player_name[:-2]

		return

	def calculate_scoring_stats(self, positional_average, lookback):

		score_count = lookback - len(self.game_scores)
		if score_count > 0:
			self.game_scores.extend([positional_average]*score_count)
		self.scoring_average = np.mean(self.game_scores)
		self.scoring_stdev = np.std(self.game_scores)

		return

	def make_projections(self, schedule_table, defense_matrix):

		schedule = schedule_table.loc[self.full_team, :]
		for opponent in schedule:
			if opponent == 'Bye':
				self.projected_scores.append(0.0)
			else:
				self.projected_scores.append(
					self.scoring_average * defense_matrix.loc[opponent, self.position]
					)

		return

	def __str__(self):

		return self.player_name + ', ' + self.position


class Simulation(object):

    def __init__(self, league_id, stats_id, year, complete_weeks, lookback, sim_count):

        self.league_id = league_id
        self.stats_id = stats_id
        self.year = year
        self.complete_weeks = complete_weeks
        self.lookback = lookback
        self.sim_count = sim_count
        self.owner_list = self.populate_owners()
        self.rank_table = self.build_rank_table()
        self.output_table = self.build_out_table()
        self.owner_list.sort(reverse=True)
        self.positional_scores = {
        						'QB': [], 'RB': [], 'WR': [],
        						'TE': [], 'K': [], 'D/ST': []
        						}
        self.positional_deviations = copy.deepcopy(self.positional_scores)

        self.team_dict = {}
        self.player_list = []
        self.populate_players()
        self.populate_stats()
        self.populate_defense_teams()
        self.calculate_player_stats()
        self.defense_matrix = self.build_defense_matrix()
        self.populate_defense_stats()
        self.schedule_table = self.build_schedule_table()
        self.populate_schedule()
        self.adjust_player_projections()
        self.set_lineups()
        self.run_simulation()
        self.calculate_percentages()
        self.finish_simulation()

    def populate_owners(self):

        pass

    def build_rank_table(self):

        table = pd.DataFrame(0, index = [owner.name_complex for owner in self.owner_list],
            columns = ['Current'] + range(1, len(self.owner_list) + 1))
        table.index.name = 'Team'
        table['Current'] = range(1, len(self.owner_list) + 1)
        return table

    def build_out_table(self):

    	columns = ['Current Wins', 'Current Rank', 'Current Points',
			'Projected Wins', 'Projected Points', 'Playoff Odds'
    		]
        table = pd.DataFrame(0, index=[owner.name_complex for owner in self.owner_list],
            columns=columns)

        return table

    def populate_players(self):

    	players = []

    	for owner in self.owner_list:
    		self.player_list.extend(owner.roster)

    	return

    def populate_stats(self):

    	url_preamble = 'http://www.fftoday.com'
    	league_url = '?LeagueID=' + self.stats_id
    	defense_url = (url_preamble + '/stats/playerstats.php?Season=' + 
    					self.year + '&PosID=99&leagueID=' + self.stats_id
    					)
    	defense_table = html.fromstring(requests.get(defense_url).text)

    	for player in self.player_list:

    		if player.position != 'D/ST':
    			last_name = player.player_name[player.player_name.find(' ') + 1:]
    			url = url_preamble + '/stats/players?Search=' + last_name
    			raw_player = None
    			raw_search = requests.get(url)

    			if raw_search.url == url:
    				raw_player = self.get_player_page(raw_search, player, league_url)
    			else:
    				raw_player = requests.get(raw_search.url + league_url)

    			html_player = html.fromstring(raw_player.text)

    			self.extract_team_info(player, html_player)

    			self.extract_games(player, html_player)

    		else:
    			for entry in defense_table.xpath('//td[@class="sort1"]/a'):
    				if player.player_name[:-5] in entry.xpath('./text()')[0]:
    					url = url_preamble + entry.xpath('./@href')[0] + self.stats_id
    					html_defense = html.fromstring(requests.get(url).text)
    					self.extract_games(player, html_defense)

    		self.positional_scores[player.position].extend(player.game_scores)

    	return

    def calculate_player_stats(self):

    	for position in self.positional_scores.iterkeys():
    		mean = np.mean(self.positional_scores[position])
    		stdev = np.std(self.positional_scores[position])
    		self.positional_scores[position] = mean
    		self.positional_deviations[position] = stdev

    	for player in self.player_list:
    		player.calculate_scoring_stats(
    			self.positional_scores[player.position], self.lookback
    			)

    	return

    def get_player_page(self, raw_search, player, league_url):

		html_search = html.fromstring(raw_search.text)
		raw_player = None
		for search_result in html_search.xpath('//span[@class="bodycontent"]'):
			result_info = search_result.xpath('./a/text()')[0]
			first_name = player.player_name[:player.player_name.find(' ')]
			if first_name in result_info and player.position in result_info:
				raw_player = requests.get('http://fftoday.com' +
				search_result.xpath('./a/@href')[0] + league_url
				)
		return raw_player

    def extract_team_info(self, player, html_player):

		raw_team = html_player.xpath('//td[@class = "update"]/text()')[0]
		full_team = raw_team[raw_team.find(',') + 2:]
		abbr_team = html_player.xpath(
					'//span[contains(text(), "Season")]/following::table[1]//tr[last()]/td[2]/text()'
					)[0]
		player.full_team = full_team
		player.abbr_team = abbr_team
		if full_team != 'Free Agent':
			self.team_dict[full_team] = abbr_team

		return

    def populate_defense_teams(self):

		for player in self.player_list:
			if player.position == 'D/ST':
				for team_name in self.team_dict.iterkeys():
					if player.player_name[:-5] in team_name:
						player.full_team = team_name
						player.team_abbr = self.team_dict[team_name]

		return

    def extract_games(self, player, html_player):
		
		for yearly_log in html_player.xpath(
			'//span[contains(text(), "Gamelog")]/following::table[1]'
			):
			temp_scores = []
			for game in yearly_log.xpath('.//tr'):
				try:
					int(game.xpath('./td[@class="sort1"]/text()')[0])
					temp_scores.append(float(game.xpath('./td[@class="sort1"]/text()')[-1]))
				except:
					continue
			player.game_scores.extend(temp_scores[::-1])

		return

    def build_defense_matrix(self):

		matrix = pd.DataFrame(0, index = self.team_dict.keys(), 
			columns = self.positional_scores.keys()
			)

		return matrix

    def populate_defense_stats(self):

		for position in constants.positional_codes.iterkeys():
			week_fraction = self.complete_weeks/float(12)
			for year in range(int(self.year), int(self.year) - 2, -1):

				url = ('http://fftoday.com/stats/fantasystats.php?Season=' + 
					str(year) + '&GameWeek=Season&PosID=' + 
					constants.positional_codes[position] + '&Side=Allowed&LeagueID=' +
					self.stats_id
					)

				defense_data = requests.get(url)
				defense_html = html.fromstring(defense_data.text)

				for row in defense_html.xpath('//tr[@class = "tableclmhdr"]/following-sibling::tr'):
					row_title = row.xpath('./td[1]/a/text()')[0]
					team = row_title[:row_title.find(' vs.')]
					if 'Chargers' in team and year == 2016:
						team = 'Los Angeles Chargers'
					points = float(row.xpath('./td[last()]/text()')[0])
					self.defense_matrix.loc[team, position] += (points * week_fraction)

				week_fraction = 1 - week_fraction
			mean = self.defense_matrix.loc[:, position].mean()
			self.defense_matrix.loc[:, position] = self.defense_matrix.loc[:,position]/mean

		return

    def build_schedule_table(self):

		schedule_table = pd.DataFrame('Bye', index = self.team_dict.keys(), 
			columns = range(1, 18)
			)

		return schedule_table

    def populate_schedule(self):

		url = 'http://fftoday.com/nfl/schedule_grid_17.html'
		raw_schedule = requests.get(url)
		html_schedule = html.fromstring(raw_schedule.text)
		
		temp_dict = {}
		for key, value in self.team_dict.items():
			temp_dict[value] = key
		
		for team in html_schedule.xpath('//td[@align = "left" and @class = "tablehdr"]'):
			team_abbr = team.xpath('./strong/text()')[0]
			if team_abbr == 'Bye':
				continue
			
			full_team = temp_dict[team_abbr]

			for index, matchup in enumerate(team.xpath('./following-sibling::td'), start = 1):
				opponent = matchup.xpath('./text()')
				if opponent:
					opponent = opponent[0].strip('@')
					self.schedule_table.loc[full_team, index] = temp_dict[opponent]

		return

    def adjust_player_projections(self):

		for player in self.player_list:
			if player.full_team != 'Free Agent':
				player.make_projections(self.schedule_table, self.defense_matrix)
			else:
				player.projected_scores = [0.0] * 17

		return

    def set_lineups(self):

		for owner in self.owner_list:
			owner.set_lineups(self)

		return

    def run_simulation(self):

        for i in range(1, self.sim_count+1):
            if i%1000 == 0:
                print i
            simulated_owners = {owner.name_complex:SimulationOwner(owner) 
                for owner in self.owner_list
                }
            self.play_games(simulated_owners)
            simulated_rankings = sorted(simulated_owners.values(),
                reverse = True
                )
            self.wild_card(simulated_rankings)
            self.update_table(simulated_rankings)

    def play_games(self, simulated_owners):

        for sim_owner in simulated_owners.itervalues():         
            for index, week_simulation in enumerate(sim_owner.simulated_points):
                opponent = simulated_owners[sim_owner.final_opponents[index]]
                if week_simulation > simulated_owners[opponent.name_complex].simulated_points[index]:
                    sim_owner.wins += 1
                elif week_simulation < simulated_owners[opponent.name_complex].simulated_points[index]:
                    sim_owner.losses += 1
            sim_owner.owner.simulated_wins.append(sim_owner.wins)
            sim_owner.owner.simulated_losses.append(sim_owner.losses)
            sim_owner.calc_win_percentage()
        return

    def wild_card(self, simulated_rankings):

        wild_card = max(simulated_rankings[5:], key = lambda sim_owner: sim_owner.total_points)
        wild_card = simulated_rankings.pop(simulated_rankings.index(wild_card))
        simulated_rankings.insert(5, wild_card)
        return

    def update_table(self, simulated_rankings):

        for rank, sim_owner in enumerate(simulated_rankings, 1):
            self.rank_table[rank][sim_owner.name_complex] += 1

    def calculate_percentages(self):

        self.rank_table.ix[:, 1:] = self.rank_table.ix[:, 1:] / float(self.sim_count) * 100
        self.rank_table['Playoff Odds'] = self.rank_table.iloc[:, 1:7].sum(axis=1)
        return

    def finish_simulation(self):

        writer = pd.ExcelWriter('playoff_odds.xlsx')
        self.rank_table.to_excel(writer)
        writer.save()

        writer = pd.ExcelWriter('power_rankings.xlsx')

        for owner in self.owner_list:
        	self.output_table.loc[owner.name_complex, 'Current Wins'] = owner.wins
        	self.output_table.loc[owner.name_complex, 'Current Rank'] = owner.current_rank
        	self.output_table.loc[owner.name_complex, 'Current Points'] = owner.total_points
        	self.output_table.loc[owner.name_complex, 'Projected Wins'] = np.mean(owner.simulated_wins)
        	self.output_table.loc[owner.name_complex, 'Projected Points'] = np.mean(owner.simulated_totals)
        	playoff_odds = self.rank_table.loc[owner.name_complex, 'Playoff Odds']
        	self.output_table.loc[owner.name_complex, 'Playoff Odds'] = playoff_odds

        self.output_table.sort(columns = 'Projected Points', ascending = False, inplace = True)

        self.output_table.to_excel(writer)
        writer.save()


class ESPNSimulation(Simulation):

    def __init__(self, league_id, stats_id, year, complete_weeks, lookback, sim_count):

        super(ESPNSimulation, self).__init__(league_id, stats_id, year, complete_weeks, lookback, sim_count)

    def populate_owners(self):

        owner_list = []    
        standings_url = ('http://games.espn.go.com/ffl/standings?leagueId=' +
                        self.league_id + '&seasonId=' + self.year)
        raw_standings = requests.get(standings_url)
        html_standings = html.fromstring(raw_standings.text)
        rank = 1
        for standings_entry in html_standings.xpath('//tr[@class="tableBody"]'):   
            name_complex = standings_entry.xpath('./td/a[@title]/@title')[0]
            id_reference = standings_entry.xpath('./td/a[@title]/@href')[0]
            ID = id_reference[string.find(id_reference, 'teamId='):]
            ID = ID[7:string.find(ID, '&seasonId=')]
            wins = int(standings_entry.xpath('./td[2]/text()')[0])
            losses = int(standings_entry.xpath('./td[3]/text()')[0])
            new_owner = Owner(
            	name_complex, ID, self.year, self.league_id, wins, losses, rank
            	)
            owner_list.append(new_owner)
            rank += 1
        return owner_list

def main():
    
    ESPNSimulation('392872', '191290', '2017', 5, 12, 10)
    '''
    league_id = raw_input('Please enter your league ID number?')
    stats_id = raw_input('Please enter your stats ID number?')
    year = (raw_input('What year is it?'))
    sim_number = int(raw_input('How many times do you want to sim the remaining games?'))
    # ESPNSimulation(league_id, sim_number)
    ESPNSimulation(league_id, stats_id, year, sim_number)
	'''
main()
