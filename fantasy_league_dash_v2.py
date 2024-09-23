import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import requests
import warnings
warnings.filterwarnings('ignore')

# ---------------------------------------------------------------------------
# Data Pull

# Get Current Gameweek
json = requests.get('https://fantasy.premierleague.com/api/bootstrap-static/').json()
dg = pd.DataFrame(json['events'])[['id', 'most_captained']]
currentgameweek = dg.loc[~dg['most_captained'].isna()]['id'].max()
nextweek = currentgameweek+1

# All Player Performance - name, team, score, fixtures, fixture difficulty
json = requests.get('https://fantasy.premierleague.com/api/bootstrap-static/').json()
elements_df = pd.DataFrame(json['elements'])[[
    'id',
    'web_name',
    'element_type',
    'team',
    'total_points',
    'chance_of_playing_next_round',
    'now_cost'
]]

elements_df = elements_df.rename(columns={'chance_of_playing_next_round':'COPNR'})

teams_df = pd.DataFrame(json['teams'])[['id','name']]
teams_df = teams_df.rename(columns={'id':'team'})

json = requests.get('https://fantasy.premierleague.com/api/fixtures/').json()
fixtures_df1 = pd.DataFrame(json)[['event', 'team_h', 'team_h_difficulty']]
fixtures_df2 = pd.DataFrame(json)[['event', 'team_a', 'team_a_difficulty']]
fixtures_df1 = fixtures_df1.rename(columns={'team_h':'team','team_h_difficulty':'MD'})
fixtures_df1['home/away'] = 1
fixtures_df2 = fixtures_df2.rename(columns={'team_a':'team','team_a_difficulty':'MD'})
fixtures_df2['home/away'] = -1
fixtures_df = pd.concat([fixtures_df1,fixtures_df2])
fixtures_df = fixtures_df.merge(teams_df, on='team', how='left')
fixtures_for_merge = fixtures_df.loc[fixtures_df['event'] == currentgameweek+1]

elements_df = elements_df.merge(fixtures_for_merge, on='team', how='left')[['id',
                                                                            'web_name',
                                                                            'element_type',
                                                                            'name',
                                                                            'total_points',
                                                                            'MD',
                                                                            'home/away',
                                                                            'COPNR',
                                                                            'now_cost']]

playersinformationdf = []
for y in elements_df['id']:
    json = requests.get(f'https://fantasy.premierleague.com/api/element-summary/{y}/').json()
    try:
        playershistoric = pd.DataFrame(json['history'])[['total_points']]
        playershistoric = playershistoric.tail(4)
        playerid = y
        averagepoints = playershistoric['total_points'].mean()

        d = {'id': playerid, '4wpoints': averagepoints}
        playershistoric = pd.DataFrame(data=[d])

        playersinformationdf.append(playershistoric)
    except:
        pass

playersinformationdf = pd.concat(playersinformationdf)

elements_df = elements_df.merge(playersinformationdf, on='id', how='left')

elements_df['COPNR'] = elements_df['COPNR'].fillna(100)
elements_df['now_cost'] = elements_df['now_cost']/10
elements_df['roi'] = elements_df['total_points']/elements_df['now_cost']
elements_df['TP'] = elements_df['4wpoints'] - elements_df['MD'] + elements_df['home/away']


di = {1:'Goalkeeper', 2:'Defender', 3:'Midfielder', 4:'Forward'}
elements_df = elements_df.replace({'element_type': di})

# upcoming fixtures - fixtures, difficulty, double gameweeks
upcoming_fixtures_df = fixtures_df.groupby(['event', 'name'])['team'].count().reset_index()
upcoming_fixtures_df = upcoming_fixtures_df.loc[upcoming_fixtures_df['team']>1]

# Get How Much Money I have in Bank
json = requests.get('https://fantasy.premierleague.com/api/entry/5521294/history').json()
currentperformance = pd.DataFrame(json['current'])
moneyinbank = currentperformance.loc[currentperformance['event'] == currentgameweek]['bank'].sum() / 10

# My Team Perfomance - name, team, score, fixture difficulty
json = requests.get(f'https://fantasy.premierleague.com/api/entry/5521294//event/{currentgameweek}/picks/').json()

myteamdf = pd.DataFrame(json['picks'])['element']
myteamdf = elements_df.loc[elements_df['id'].isin(myteamdf)].sort_values('total_points', ascending=False)
myteamdf['replacement_budget'] = myteamdf['now_cost'] + moneyinbank

# alternative players logic, single swap out

top_players = elements_df.sort_values(by='TP', ascending=False)
teamtotals = myteamdf.groupby('name')['id'].count().reset_index()

alternativeplayersdf = []
for i in myteamdf['id'].unique():
    alternativebudget = myteamdf.loc[(myteamdf['id'] == i)]['replacement_budget'].sum()
    alternativeposition = myteamdf.loc[(myteamdf['id'] == i)]['element_type'].sum()
    alternativeplaverlist = top_players.loc[(top_players['now_cost'] <= alternativebudget)
                                             & (top_players['element_type'] == alternativeposition)
                                             & (top_players['COPNR'] == 100)
                                             & (~top_players['id'].isin(myteamdf['id'].unique()))]
    for y in alternativeplaverlist['id']:
        filteraltplayer = top_players.loc[top_players['id'] == y]
        if teamtotals.loc[teamtotals['name'].isin(myteamdf.loc[(myteamdf['id'] == i)]['name'])]['id'].sum() == 3:
            if teamtotals.loc[teamtotals['name'].isin(myteamdf.loc[(myteamdf['id'] == i)]['name'])]['id'].sum() - filteraltplayer.groupby('name')['id'].count().sum() <= 3:
                alternativeplaver = filteraltplayer
                break
        elif teamtotals.loc[teamtotals['name'].isin(filteraltplayer['name'])]['id'].sum() + filteraltplayer.groupby('name')['id'].count().sum() <= 3:
            alternativeplaver = filteraltplayer
            break
        else:
            alternativeplaver = filteraltplayer
    alternativeplaver = alternativeplaver.rename(
        columns={'id': 'replacement_id', 'TP': 'Alt TP', 'web_name':'Alt Web Name', 'name':'Alt Team'})
    alternativeplaver = alternativeplaver[['replacement_id', 'Alt TP', 'Alt Web Name', 'Alt Team']]
    alternativeplaver['replace_with_id'] = i
    alternativeplayersdf.append(alternativeplaver)
alternativeplayersdf = pd.concat(alternativeplayersdf)
myteamdf = myteamdf.merge(alternativeplayersdf, left_on='id', right_on='replace_with_id')
myteamdf['Opp Cost'] = myteamdf['Alt TP'] - myteamdf['TP']
altplayer = myteamdf.sort_values('Opp Cost', ascending=False)[['Alt Web Name', 'Alt Team', 'web_name', 'Opp Cost']]
altplayer = altplayer.rename(columns={'web_name':'replace out for'})

# alternative players logic, dual swap out
dualswapdic = {}
for x in myteamdf['element_type'].unique():
    try:
        # top player to get in
        TPalt = top_players.loc[(top_players['element_type'] == x) & (~top_players['id'].isin(myteamdf['id'].unique()))].head(1)
        TPaltTP = TPalt['TP'].sum()
        TPalcost = TPalt['now_cost'].sum()
        myteamdf.loc[myteamdf['element_type'] ==x , 'secondplayer logic'] = myteamdf['TP'] - TPaltTP
        #replace with
        replacewith = myteamdf.loc[(myteamdf['element_type'] ==x) & (myteamdf['secondplayer logic'] < 0)].sort_values('now_cost', ascending=False).head(1)
        replacewithmoney = replacewith['replacement_budget'].sum()
        moneydeficit = TPalcost - replacewithmoney
        myteamdf.loc[(myteamdf['id'] != replacewith['id'].sum()), 'secondplayer deficit cover'] = myteamdf['now_cost'] - moneydeficit
        secondswapout = myteamdf.loc[(myteamdf['secondplayer deficit cover'] >= top_players['now_cost'].min()) & (myteamdf['id'] != replacewith['id'].sum())]
        secondswapoutalt = []
        for i in secondswapout['id'].unique():
            alternativebudget = myteamdf.loc[(myteamdf['id'] == i)]['secondplayer deficit cover'].sum()
            alternativeposition = myteamdf.loc[(myteamdf['id'] == i)]['element_type'].sum()
            alternativeplaverlist = top_players.loc[(top_players['now_cost'] <= alternativebudget)
                                                    & (top_players['element_type'] == alternativeposition)
                                                    & (top_players['COPNR'] == 100)
                                                    & (~top_players['id'].isin(myteamdf['id'].unique()))]
            for y in alternativeplaverlist['id']:
                filteraltplayer = top_players.loc[top_players['id'] == y]
                if teamtotals.loc[teamtotals['name'].isin(myteamdf.loc[(myteamdf['id'] == i)]['name'])]['id'].sum() == 3:
                    if teamtotals.loc[teamtotals['name'].isin(myteamdf.loc[(myteamdf['id'] == i)]['name'])]['id'].sum() - \
                            filteraltplayer.groupby('name')['id'].count().sum() <= 3:
                        alternativeplaver = filteraltplayer
                        break
                elif teamtotals.loc[teamtotals['name'].isin(filteraltplayer['name'])]['id'].sum() + \
                        filteraltplayer.groupby('name')['id'].count().sum() <= 3:
                    alternativeplaver = filteraltplayer
                    break
                else:
                    alternativeplaver = filteraltplayer
            alternativeplaver = alternativeplaver.rename(
                columns={'id': 'second_player_replacement_id', 'TP': 'second_Alt TP', 'web_name': 'second_Alt Web Name', 'name': 'second_Alt Team'})
            alternativeplaver = alternativeplaver[['second_player_replacement_id', 'second_Alt TP', 'second_Alt Web Name', 'second_Alt Team']]
            alternativeplaver['second_replace_with_id'] = i
            alternativeplaver['opp cost'] = alternativeplaver['second_Alt TP'].sum() -  myteamdf.loc[(myteamdf['id'] == i)]['TP'].sum()
            secondswapoutalt.append(alternativeplaver)
        secondswapoutalt = pd.concat(secondswapoutalt)
        secondswapoutalt = secondswapoutalt.loc[secondswapoutalt['opp cost'] == secondswapoutalt['opp cost'].max()]
        secondswapoutalt['type'] = 'second swapout'

        secondkeydf = TPalt.rename(columns={'id':'second_player_replacement_id','TP':'second_Alt TP', 'web_name':'second_Alt Web Name', 'name': 'second_Alt Team'})
        secondkeydf = secondkeydf[['second_player_replacement_id', 'second_Alt TP', 'second_Alt Web Name', 'second_Alt Team']]
        secondkeydf['second_replace_with_id'] = replacewith['id'].sum()
        secondkeydf['opp cost'] = secondkeydf['second_Alt TP'].sum() - replacewith['TP'].sum()
        secondkeydf['type'] = 'main swapout'

        secondkeydf = pd.concat([secondkeydf,secondswapoutalt])
        secondkeydf = myteamdf[['id', 'web_name', 'name', 'element_type', 'TP']].merge(
            secondkeydf[['second_player_replacement_id', 'second_replace_with_id', 'second_Alt Web Name', 'second_Alt TP','second_Alt Team']], left_on='id',
            right_on='second_replace_with_id', how='left')
        secondkeydf.loc[~secondkeydf['second_player_replacement_id'].isna(), 'player Out'] = secondkeydf['web_name']
        secondkeydf['second_replace_with_id'] = secondkeydf['second_replace_with_id'].fillna(secondkeydf['id'])
        secondkeydf['second_Alt Web Name'] = secondkeydf['second_Alt Web Name'].fillna(secondkeydf['web_name'])
        secondkeydf['second_Alt TP'] = secondkeydf['second_Alt TP'].fillna(secondkeydf['TP'])
        secondkeydf['second_Alt Team'] = secondkeydf['second_Alt Team'].fillna(secondkeydf['name'])
        secondkeydf = secondkeydf[['second_player_replacement_id', 'player Out', 'second_replace_with_id', 'second_Alt Web Name', 'second_Alt TP', 'second_Alt Team', 'element_type']]
        dualswapdic[x] = secondkeydf
    except:
        pass

scenariopicker = pd.concat(dualswapdic).reset_index().groupby('level_0')['second_Alt TP'].sum().reset_index()
scenariopicker = scenariopicker.loc[scenariopicker['second_Alt TP']==scenariopicker['second_Alt TP'].max()]['level_0'].sum()
dualswapoutdf = dualswapdic[scenariopicker]
dualswapoutdf = dualswapoutdf.rename(columns={'second_Alt Web Name':'web_name', 'second_Alt TP':'TP', 'second_Alt Team':'name'})

# Enemy player stats - scores per gameweek

names = ["James_Curran", "Sam", "Sean", "Chris", "James_Cowell", "Tor-Elesh", 'Ross', 'Patrick']
ids = ['3578550', '4074556', '5983095', '5207915', '6222620', '5521294', '5775103', '218856']

leagueperformance = []
for x, z in zip(names, ids):
    json = requests.get(f'https://fantasy.premierleague.com/api/entry/{z}/history').json()
    competitiveperformance = pd.DataFrame(json['current'])[['event', 'points']]
    competitiveperformance['points'] = competitiveperformance['points'].cumsum()
    competitiveperformance['name'] = x
    leagueperformance.append(competitiveperformance)
leagueperformance = pd.concat(leagueperformance)

best_replacement_team=[]
cheap_players=[]
budget = 82
team_limit = 11
cheap_player_limit = 4
injured = elements_df.loc[elements_df['COPNR'] != 100]['id']
gk = 2
df = 5
md = 5
fwd = 3

Ar = 3
Av = 3
bm = 3
bf = 3
br = 3
ch = 3
cp = 3
Et = 3
Fh = 3
Iw = 3
Lc = 3
LP = 3
MC = 3
MU = 3
NC = 3
NM = 3
SH = 3
Su = 3
WH = 3
W = 3
positions = {'Goalkeeper':gk, 'Defender':df, 'Midfielder':md, 'Forward':fwd}
teams = {'Arsenal':Ar, 'Aston Villa':Av, 'Bournemouth':bm, 'Brentford':bf, 'Brighton':br,
       'Chelsea':ch, 'Crystal Palace':cp, 'Everton':Et, 'Fulham':Fh, 'Ipswich':Iw,
       'Leicester':Lc, 'Liverpool':LP, 'Man City':MC, 'Man Utd':MU, 'Newcastle':NC,
       "Nott'm Forest":NM, 'Southampton':SH, 'Spurs':Su, 'West Ham':WH, 'Wolves':W}
for player in top_players['id']:
    if len(best_replacement_team) < team_limit\
            and player not in injured.to_list() \
            and budget >= elements_df.loc[elements_df['id'] == player]['now_cost'].sum()\
            and positions[elements_df.loc[elements_df['id'] == player]['element_type'].sum()] > 0\
            and teams[elements_df.loc[elements_df['id'] == player]['name'].sum()] > 0:
        best_replacement_team.append(player)
        budget -= elements_df.loc[elements_df['id'] == player]['now_cost'].sum()
        positions[elements_df.loc[elements_df['id'] == player]['element_type'].sum()] = positions[elements_df.loc[elements_df['id'] == player]['element_type'].sum()] - 1
        teams[elements_df.loc[elements_df['id'] == player]['name'].sum()] = teams[elements_df.loc[elements_df['id'] == player]['name'].sum()] - 1
    else:
        for player in top_players['id']:
            if len(cheap_players) < cheap_player_limit \
                    and player not in injured.to_list() \
                    and player in elements_df.loc[elements_df['now_cost'] == 4.5]['id'].unique() \
                    and positions[elements_df.loc[elements_df['id'] == player]['element_type'].sum()] > 0 \
                    and teams[elements_df.loc[elements_df['id'] == player]['name'].sum()] > 0:
                cheap_players.append(player)
                positions[elements_df.loc[elements_df['id'] == player]['element_type'].sum()] = positions[elements_df.loc[elements_df['id'] == player]['element_type'].sum()] - 1
                teams[elements_df.loc[elements_df['id'] == player]['name'].sum()] = teams[elements_df.loc[elements_df['id'] == player]['name'].sum()] - 1

final_team = elements_df.loc[elements_df['id'].isin(best_replacement_team) | elements_df['id'].isin(cheap_players)].sort_values('total_points', ascending=False)

# Advise on Scenario
myteamdf.loc[myteamdf['Opp Cost'] != myteamdf['Opp Cost'].max(), 'Primary Scenario'] = myteamdf['TP']
myteamdf['Primary Scenario'] = myteamdf['Primary Scenario'].fillna(myteamdf['Alt TP'])
singpleplayerout = myteamdf.loc[myteamdf['Opp Cost'] == myteamdf['Opp Cost'].max()]['web_name'].sum()
singeplayerin = myteamdf.loc[myteamdf['Opp Cost'] == myteamdf['Opp Cost'].max()]['Alt Web Name'].sum()
primaryscenario = myteamdf['Primary Scenario'].sum()

twoplayerswapscenario = dualswapoutdf['TP'].sum() - 4
twoplayeroutone = dualswapoutdf.loc[~dualswapoutdf['player Out'].isna()].head(1)['player Out'].sum()
twoplayerouttwo = dualswapoutdf.loc[~dualswapoutdf['player Out'].isna()].tail(1)['player Out'].sum()
twoplayerinone = dualswapoutdf.loc[~dualswapoutdf['player Out'].isna()].head(1)['web_name'].sum()
twoplayerintwo = dualswapoutdf.loc[~dualswapoutdf['player Out'].isna()].tail(1)['web_name'].sum()

if twoplayerswapscenario > primaryscenario:
    displaystring = f'''For Gameweek {nextweek} it is advised to use the dual player swapout and take the 4point penalty cost, 
    this has a higher 4 week average yield of {(twoplayerswapscenario - primaryscenario)} points. 
    It is therefore advice to transfer out {twoplayeroutone} for {twoplayerinone} and {twoplayerouttwo} for {twoplayerintwo}'''
else:
    displaystring = f'''For {nextweek} it is advised to go with the single player swapout and avoid the 4point penalty cost. 
    This strategy has a higher 4 week average yield of {(primaryscenario - twoplayerswapscenario)} points.
    By swapping out {singpleplayerout} and replacing with {singeplayerin}'''

#-----------------------------------------------------------------------------------------------------------------------
#Dashboarding
st.set_page_config(layout='wide', initial_sidebar_state='expanded')

st.write("""
'FPL Dashboard, `version 2`'
""")

st.markdown('### Team Performance')
st.markdown(f'Advising for Gameweek: {nextweek.astype(str)}')
st.markdown(displaystring)
#Row B

c1, c2 = st.columns((5,5))
with c1:
    st.markdown('Single Player Swapout')
    st.dataframe(
        myteamdf.sort_values('TP', ascending=False).reset_index()[['web_name','COPNR','name','element_type', 'MD', 'Alt Web Name', 'Alt Team', 'Opp Cost']]
        .style.format({'Opp Cost': '{:.2f}'.format,
                      'COPNR': '{:.0f}'.format})
        .applymap(lambda s: np.where(s >= 4, "background-color:red", None), subset=['MD'])
        .applymap(lambda s: np.where(s <= 2, "background-color:green", None), subset=['MD'])
        .applymap(lambda s: np.where(s < 100, "background-color:red", None), subset=['COPNR'])
        .applymap(lambda s: np.where(s == myteamdf['Opp Cost'].max(), "background-color:red", None), subset=['Opp Cost']),
        height = (len(myteamdf) + 1) * 35 + 3,
        column_config = {"Opp Cost": st.column_config.NumberColumn(format="%.2f")})
with c2:
    st.markdown('Dual Player Swapout')
    st.dataframe(
        dualswapoutdf.sort_values('TP', ascending=False).reset_index()[['player Out','web_name','name','element_type']],
        height=(len(dualswapoutdf) + 1) * 35 + 3)

g1, g2 = st.columns((3,7))

with g1:
    st.markdown('Wildcard Full Team Swapout')
    st.dataframe(
        final_team.sort_values('TP', ascending=False)[['web_name','name','element_type']],
        height=(len(final_team) + 1) * 35 + 3,
        hide_index=True)
with g2:
    st.markdown('### League Performance')

    fig = px.line(leagueperformance,
                            x="event",
                            y="points",
                            color='name',
                            template = 'plotly_dark',
                            markers=False)
    for d in fig['data']:
        if d['name'] == 'Tor-Elesh':
            d['line']['color'] = 'red'
        else:
            d['line']['color'] = 'lightgrey'


    st.plotly_chart(fig, use_container_width=True)
