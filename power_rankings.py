# -*- coding: utf-8 -*-
# @Author: Charles Starr
# @Date:   2017-09-23 16:30:04
# @Last Modified by:   Charles Starr
# @Last Modified time: 2017-09-24 17:41:36

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


class Owner(object):
    #create an owner class for every owner in the standings table

    def __init__(self, name_complex, ID, year, league_id, wins, losses, rank):
        #initialize variables that will be needed for simulation
        self.name_complex = name_complex
        self.ID = ID
        self.year = year
        self.league_id = league_id
        self.wins = wins
        self.losses = losses
        self.current_rank = rank     
        self.scores = [] 
        self.final_opponents = self.schedule_data()
        self.win_percentage = self.calc_win_percentage() 
        self.total_points = np.sum(self.scores)
        self.roster = self.populate_roster()
        
    def schedule_data(self):
        #get info about games played and games remaining
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

        self.win_percentage = float(self.wins)/len(self.scores)

    def populate_roster(self):

    	roster_url = ('http://games.espn.com/ffl/clubhouse?leagueId=' + 
    		self.league_id + '&teamId=' + self.ID + '&seasonId=' + self.year
    		)
    	raw_roster = requests.get(roster_url)
    	html_roster = html.fromstring(raw_roster.text)
    	roster = []

    	for player_row in html_roster.xpath('//tr[contains(@class, "pncPlayerRow")]'):
    		if player_row.xpath('./td[1]/text()')[0] != 'IR':
    			player_name = player_row.xpath('./td[2]/a/text()')[0]
    			position_raw = player_row.xpath('./td[2]/text()')[0]
    			position = position_raw[position_raw.find(u'\xa0') + 1:].strip(u'\xa0')
    			roster.append(Player(player_name, position))

    	return roster

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


class Player(object):

	def __init__(self, player_name, position):

		self.player_name = player_name
		self.position = position
		self.game_scores = []
		self.name_trim()

	def name_trim(self):

		if 'Jr.' in self.player_name or 'Sr.' in self.player_name:
			self.player_name = self.player_name[:-4]

	def __str__(self):

		return self.player_name + ', ' + self.position


class Simulation(object):

    def __init__(self, league_id, stats_id, year, sim_count):

        self.league_id = league_id
        self.stats_id = stats_id
        self.year = year
        self.sim_count = sim_count
        self.owner_list = self.populate_owners()
        self.rank_table = self.build_table()
        self.owner_list.sort(reverse=True)
        self.positional_scores = {
        						'QB':[], 'RB':[], 'WR':[], 
        						'TE':[], 'K':[], 'D/ST':[]
        						}
        self.player_list = self.populate_players()
        self.populate_stats()
        self.run_simulation()
        self.calculate_percentages()
        self.finish_simulation()

    def populate_owners(self):

        pass

    def build_table(self):

    	columns = ['Team', 'Current Record', 'Current Rank', 'Current Points',
    		'Points Rank', 'Projected Record', 'Projected Points', 'Playoff Odds'
    		]
        table = pd.DataFrame(0, index = [owner.name_complex for owner in self.owner_list],
            columns = columns )
        table.index.name = 'Team'
        table['Current'] = range(1, len(self.owner_list) + 1)
        return table

    def populate_players(self):

    	players = []

    	for owner in self.owner_list:
    		players.extend(owner.roster)

    	return players

    def populate_stats(self):

    	league_url = '?LeagueID=' + self.stats_id
    	for player in self.player_list:
    		game_log = []
    		print player.player_name
    		if player.position != 'D/ST':
    			first_name = player.player_name[:player.player_name.find(' ')]
    			last_name = player.player_name[player.player_name.find(' ') + 1:]
    			url = 'http://fftoday.com/stats/players?Search=' + last_name
    			raw_player = None
    			raw_search = requests.get(url)
    			if raw_search.url == url:
    				raw_player = self.get_player_page(raw_search)
    			else:
    				raw_player = requests.get(raw_search.url + league_url)
    			print 'ok'
    			html_player = html.fromstring(raw_player.text)
    			for yearly_log in html_player.xpath('//span[contains(text(), "Gamelog")]/following::table[1]'):
    				temp_games = self.extract_games(yearly_log)
    				game_log.extend(temp_games[::-1])
    		player.game_scores = game_log
    		print player.game_scores

    def get_player_page(self, raw_search):

   		html_search = html.fromstring(raw_search.text)
   		raw_player = None
		for search_result in html_search.xpath('//span[@class="bodycontent"]'):
			result_info = search_result.xpath('./a/text()')[0]
			if first_name in result_info and player.position in result_info:
				raw_player = requests.get('http://fftoday.com' +
				search_result.xpath('./a/@href')[0] + league_url
				)
		return raw_player

	def extract_games(self, yearly_log):
		game_scores = []
		for game in yearly_log.xpath('.//tr'):
			try:
				int(game.xpath('./td[@class="sort1"]/text()')[0])
				game_scores.append(float(game.xpath('./td[@class="sort1"]/text()')[-1]))
			except:
				continue
		return game_scores

	def run_simulation(self):
		pass

    def play_games(self, simulated_owners):

        for sim_owner in simulated_owners.itervalues():         
            for index, week_simulation in enumerate(sim_owner.simulated_points):
                opponent = simulated_owners[sim_owner.final_opponents[index]]
                if week_simulation > simulated_owners[opponent.name_complex].simulated_points[index]:
                    sim_owner.wins += 1
                elif week_simulation < simulated_owners[opponent.name_complex].simulated_points[index]:
                    sim_owner.losses += 1
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
        return

    def finish_simulation(self):

        writer = pd.ExcelWriter('classes_test.xlsx')
        self.rank_table.to_excel(writer)
        writer.save()


class ESPNSimulation(Simulation):

    def __init__(self, league_id, stats_id, year, sim_count):

        super(ESPNSimulation, self).__init__(league_id, stats_id, year, sim_count)

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
    
    ESPNSimulation('392872', '191290', '2017', 10)
    '''
    league_id = raw_input('Please enter your league ID number?')
    stats_id = raw_input('Please enter your stats ID number?')
    year = (raw_input('What year is it?'))
    sim_number = int(raw_input('How many times do you want to sim the remaining games?'))
    #ESPNSimulation(league_id, sim_number)
    ESPNSimulation(league_id, stats_id, year, sim_number)
	'''
main()