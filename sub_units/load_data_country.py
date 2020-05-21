import pandas as pd
import numpy as np
import os
import datetime
import requests
from tqdm import tqdm
from collections import Counter

#####
# Step 1: Update counts data
#####

# from https://github.com/CSSEGISandData/COVID-19/tree/master/csse_covid_19_data/csse_covid_19_daily_reports

# # get today's date
# yesterdays_date_str = (datetime.date.today() - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
# print(f'Yesterday: {yesterdays_date_str}')
# yesterdays_date_str_for_JHU_data = (datetime.date.today() - datetime.timedelta(days=1)).strftime('%m-%d-%Y')
# print(f'Yesterday: {yesterdays_date_str}')
# 
# url = f"https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_daily_reports/{yesterdays_date_str_for_JHU_data}.csv"
# r = requests.get(url, allow_redirects=True)
# with open(f'source_data/csse_covid_19_daily_reports/{yesterdays_date_str_for_JHU_data}.csv', 'w') as f:
#     f.write(r.content.decode("utf-8"))

######
# Step 2: Process Data
######

map_state_to_series = dict()

data_dir = os.path.join('source_data', 'csse_covid_19_daily_reports')
onlyfiles = [f for f in os.listdir(data_dir) if os.path.isfile(os.path.join(data_dir, f))]

list_of_small_dataframes = list()
for file in tqdm(sorted(onlyfiles)):
    if not file.endswith('.csv'):
        continue
    full_filename = os.path.join(data_dir, file)
    tmp_count_data = pd.read_csv(os.path.join(data_dir, file))
    tmp_count_data.rename(columns={'Country_Region': 'Country/Region', 'Province_State': 'Province/State'},
                          inplace=True)
    print(f'processing file {full_filename} with {len(tmp_count_data)} rows...')
    tmp_count_data['date'] = datetime.datetime.strptime(file[:-4], '%m-%d-%Y')
    list_of_small_dataframes.append(tmp_count_data)

# Filter out data associated with provinces
full_count_data = pd.concat(list_of_small_dataframes)
null_provice_inds = [i for i, x in enumerate(full_count_data['Province/State']) if type(x)!=str]
full_count_data = full_count_data.iloc[null_provice_inds]
full_count_data = full_count_data.groupby(['date', 'Country/Region'])[['Confirmed', 'Deaths']].sum().reset_index()
full_count_data.rename(columns={'Country/Region': 'state', 'Confirmed': 'positive', 'Deaths': 'deceased'},
                       inplace=True)

# germany_inds = [i for i, x in enumerate(full_count_data['country']) if x == 'France']
# date_sorted_inds = sorted(germany_inds, key=lambda x: full_count_data.iloc[x]['date'])
# full_count_data.iloc[date_sorted_inds[-10:]]

# data munging gets daily-differences differences by state
for state in sorted(set(full_count_data['state'])):
    state_iloc = [i for i, x in enumerate(full_count_data['state']) if x == state]
    state_iloc = sorted(state_iloc, key=lambda x: full_count_data.iloc[x]['date'])

    cases_series = pd.Series({full_count_data.iloc[i]['date']: full_count_data.iloc[i]['cases'] for i in state_iloc})
    deaths_series = pd.Series({full_count_data.iloc[i]['date']: full_count_data.iloc[i]['deaths'] for i in state_iloc})

    cases_series.index = pd.DatetimeIndex(cases_series.index)
    deaths_series.index = pd.DatetimeIndex(deaths_series.index)

    cases_diff = cases_series.diff()
    deaths_diff = deaths_series.diff()

    map_state_to_series[state] = {'cases_series': cases_series,
                                  'deaths_series': deaths_series,
                                  'cases_diff': cases_diff,
                                  'deaths_diff': deaths_diff}

def get_state_data(state,
                   opt_smoothing=False):

    #TODO: get actual population
    
    # population = map_state_to_population[state]
    population = 1e10
    count_data = map_state_to_series[state]['cases_series'].values
    n_count_data = np.prod(count_data.shape)
    print(f'# data points: {n_count_data}')

    min_date = min(list(map_state_to_series[state]['cases_series'].index))

    # format count_data into I and S values for SIR Model
    infected = [x for x in count_data]
    susceptible = [population - x for x in count_data]
    dead = [x for x in map_state_to_series[state]['deaths_series'].values]

    ####
    # Do three-day smoothing
    ####

    new_tested = [infected[0]] + [infected[i] - infected[i - 1] for i in
                                  range(1, len(infected))]
    new_dead = [dead[0]] + [dead[i] - dead[i - 1] for i in
                            range(1, len(dead))]

    if opt_smoothing:
        print('Smoothing the data...')
        new_vals = [None] * len(new_tested)
        for i in range(len(new_tested)):
            new_vals[i] = sum(new_tested[slice(max(0, i - 1), min(len(new_tested), i + 2))]) / 3
            # if new_vals[i] < 1 / 3:
            #     new_vals[i] = 1 / 100  # minimum value
        new_tested = new_vals.copy()
        new_vals = [None] * len(new_dead)
        for i in range(len(new_dead)):
            new_vals[i] = sum(new_dead[slice(max(0, i - 1), min(len(new_dead), i + 2))]) / 3
            # if new_vals[i] < 1 / 3:
            #     new_vals[i] = 1 / 100  # minimum value
        new_dead = new_vals.copy()
    else:
        print('NOT smoothing the data...')

    infected = list(np.cumsum(new_tested))
    dead = list(np.cumsum(new_dead))

    print('new_tested')
    print(new_tested)
    print('new_dead')
    print(new_dead)

    ####
    # Put it all together
    ####

    series_data = np.vstack([susceptible, infected, dead]).T

    if 'sip_date' in map_state_to_series:
        sip_date = map_state_to_series[state]['sip_date']
    else:
        sip_date = None

    return {'series_data': series_data,
            'population': population,
            'sip_date': sip_date,
            'min_date': min_date}
