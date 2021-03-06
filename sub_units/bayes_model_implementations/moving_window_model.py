from sub_units.bayes_model import BayesModel, ApproxType
import numpy as np
import pandas as pd
import datetime
import scipy as sp
import pymc3 as pm
import joblib
import os
from os import path
import matplotlib
import matplotlib.pyplot as plt

plt.style.use('seaborn-darkgrid')
matplotlib.use('Agg')
import matplotlib.dates as mdates


class MovingWindowModel(BayesModel):

    # add model_type_str to kwargs when instantiating super
    def __init__(self,
                 state,
                 moving_window_size=21,
                 timeseries_length_in_days=28,
                 optimizer_method='SLSQP',
                 opt_simplified=False,
                 model_type_name=None,
                 **kwargs):

        if model_type_name is None:
            model_type_name = f'moving_window_{moving_window_size}_days'

        if opt_simplified:
            model_approx_types = [ApproxType.SM]  # SM_acc comes along for the ride with SM
            print('Doing simplified models...')
        else:
            model_approx_types = [ApproxType.CF, ApproxType.NDT_Hess, ApproxType.NDT_Jac, ApproxType.BS, ApproxType.LS, ApproxType.MCMC, ApproxType.SM, ApproxType.PyMC3]
            print('Doing all models...')

        # these kwargs will be added as object attributes
        kwargs.update({'model_type_name': model_type_name,
                       'moving_window_size': moving_window_size,
                       'optimizer_method': optimizer_method,
                       'model_approx_types': model_approx_types,
                       'opt_simplified': opt_simplified,
                       'timeseries_length_in_days': timeseries_length_in_days,
                       'plot_two_vals': None, #['positive_slope', 'positive_intercept']
                       })
        super(MovingWindowModel, self).__init__(state, **kwargs)

        ind1 = max(self.day_of_threshold_met_case, len(self.series_data) - moving_window_size)
        self.cases_indices = list(range(ind1, len(self.series_data)))
        ind1 = max(self.day_of_threshold_met_death, len(self.series_data) - moving_window_size)
        self.deaths_indices = list(range(ind1, len(self.series_data)))

        # dont need to filter out zero-values since we now add the logarithm offset
        # self.cases_indices = [i for i in cases_indices if self.data_new_tested[i] > 0]
        # self.deaths_indices = [i for i in deaths_indices if self.data_new_dead[i] > 0]

    def run_simulation(self, in_params, offset=0):
        '''
        run combined ODE and convolution simulation
        :param params: dictionary of relevant parameters
        :return: N
        '''

        params = self.convert_params_as_list_to_dict(in_params)

        params.update(self.static_params)
        contagious = np.array([None] * len(self.t_vals))  # this guy doesn't matter for MovingWindowModel

        # do intercept at the beginning of moving window
        intercept_t_val = self.max_date_in_days - self.moving_window_size - offset
        xzero_positive_count = np.exp(intercept_t_val * params['positive_slope'])
        xzero_deceased_count = np.exp(intercept_t_val * params['deceased_slope'])
        positive = np.maximum(np.array(np.exp(self.t_vals * params['positive_slope'])) * np.array(
            (params['positive_intercept'] - self.log_offset) / xzero_positive_count), 0)
        deceased = np.maximum(np.array(np.exp(self.t_vals * params['deceased_slope'])) * np.array(
            (params['deceased_intercept'] - self.log_offset) / xzero_deceased_count), 0)

        # positive = np.array(np.exp(self.t_vals * params['positive_slope'])) * params['positive_intercept']
        # deceased = np.array(np.exp(self.t_vals * params['deceased_slope'])) * params['deceased_intercept']

        # for i in range(len(positive)):
        #     if i % 7 == 0:
        #         positive[i] *= params['day0_multiplier']
        #         deceased[i] *= params['day0_multiplier']
        #     if i % 7 == 1:
        #         positive[i] *= params['day1_multiplier']
        #         deceased[i] *= params['day1_multiplier']
        #     if i % 7 == 2:
        #         positive[i] *= params['day2_multiplier']
        #         deceased[i] *= params['day2_multiplier']
        #     if i % 7 == 3:
        #         positive[i] *= params['day3_multiplier']
        #         deceased[i] *= params['day3_multiplier']
        #     if i % 7 == 4:
        #         positive[i] *= params['day4_multiplier']
        #         deceased[i] *= params['day4_multiplier']
        #     if i % 7 == 5:
        #         positive[i] *= params['day5_multiplier']
        #         deceased[i] *= params['day5_multiplier']
        #     if i % 7 == 6:
        #         positive[i] *= params['day6_multiplier']
        #         deceased[i] *= params['day6_multiplier']

        for i in range(len(positive)):
            if i % 7 == 0:
                positive[i] *= params['day0_positive_multiplier']
                deceased[i] *= params['day0_deceased_multiplier']
            if i % 7 == 1:
                positive[i] *= params['day1_positive_multiplier']
                deceased[i] *= params['day1_deceased_multiplier']
            if i % 7 == 2:
                positive[i] *= params['day2_positive_multiplier']
                deceased[i] *= params['day2_deceased_multiplier']
            if i % 7 == 3:
                positive[i] *= params['day3_positive_multiplier']
                deceased[i] *= params['day3_deceased_multiplier']
            if i % 7 == 4:
                positive[i] *= params['day4_positive_multiplier']
                deceased[i] *= params['day4_deceased_multiplier']
            if i % 7 == 5:
                positive[i] *= params['day5_positive_multiplier']
                deceased[i] *= params['day5_deceased_multiplier']
            if i % 7 == 6:
                positive[i] *= params['day6_positive_multiplier']
                deceased[i] *= params['day6_deceased_multiplier']

        return np.vstack([np.squeeze(contagious), positive[:contagious.size], deceased[:contagious.size]])

    def _get_log_likelihood_precursor(self,
                                      in_params,
                                      data_new_tested=None,
                                      data_new_dead=None,
                                      cases_bootstrap_indices=None,
                                      deaths_bootstrap_indices=None):
        '''
        Obtains the precursors for obtaining the log likelihood for a given parameter dictionary
          Used for self._errfunc_for_least_squares (error function for scipy.optimize.least_squares)
          and self.get_log_likelihood (neg. loss function for scipy.optimize.minimize(method='SLSQP'))
        :param in_params: dictionary or list of parameters
        :param cases_bootstrap_indices: bootstrap indices when applicable
        :param deaths_bootstrap_indices:  bootstrap indices when applicable
        :param cases_bootstrap_indices: which indices to include in the likelihood?
        :param deaths_bootstrap_indices: which indices to include in the likelihood?
        :return: tuple of lists: distances, other errors, and simulated solution
        '''

        # convert from list to dictionary (for compatibility with the least-sq solver
        params = self.convert_params_as_list_to_dict(in_params)

        if data_new_tested is None:
            data_new_tested = self.data_new_tested
        if data_new_dead is None:
            data_new_dead = self.data_new_dead

        if cases_bootstrap_indices is None:
            cases_bootstrap_indices = self.cases_indices[-self.moving_window_size:]
        if deaths_bootstrap_indices is None:
            deaths_bootstrap_indices = self.deaths_indices[-self.moving_window_size:]

        # timer = Stopwatch()
        sol = self.run_simulation(params)
        new_tested_from_sol = sol[1]
        new_deceased_from_sol = sol[2]
        # print(f'Simulation took {timer.elapsed_time() * 100} ms')
        # timer = Stopwatch()

        actual_tested = [np.log(data_new_tested[i] + self.log_offset) for i in cases_bootstrap_indices]
        predicted_tested = [np.log(new_tested_from_sol[i + self.burn_in] + self.log_offset) for i in
                            cases_bootstrap_indices]
        actual_dead = [np.log(data_new_dead[i] + self.log_offset) for i in deaths_bootstrap_indices]
        predicted_dead = [np.log(new_deceased_from_sol[i + self.burn_in] + self.log_offset) for i in
                          deaths_bootstrap_indices]

        new_tested_dists = [predicted_tested[i] - actual_tested[i] for i in range(len(predicted_tested))]
        new_dead_dists = [predicted_dead[i] - actual_dead[i] for i in range(len(predicted_dead))]

        tested_vals = [data_new_tested[i] for i in cases_bootstrap_indices]
        deceased_vals = [data_new_dead[i] for i in deaths_bootstrap_indices]
        other_errs = list()

        return new_tested_dists, new_dead_dists, other_errs, sol, tested_vals, deceased_vals, \
               predicted_tested, actual_tested, predicted_dead, actual_dead

    # @staticmethod
    # def print_var_inspection(exec_statement):
    #     print(exec_statement + ':', eval(exec_statement))

    def render_statsmodels_fit_timeseries(self, opt_simplified=False):

        use_min_date = self.min_date + datetime.timedelta(days=self.day_of_threshold_met_case - 10)
        use_max_date = self.max_date
        timeseries_length_in_days = (use_max_date - use_min_date).days
        for offset in reversed(range(timeseries_length_in_days)):
            opt_plot = False
            if offset == 0:
                opt_plot = True
            self._render_statsmodels_fit_sub(opt_simplified=opt_simplified, offset=offset, opt_plot=opt_plot, opt_print=False)

    def render_statsmodels_fit(self, opt_simplified=False, offset=7):
        self._render_statsmodels_fit_sub(opt_simplified=opt_simplified, offset=offset, opt_plot=not opt_simplified)
        self._render_statsmodels_fit_sub(opt_simplified=opt_simplified, offset=0, opt_plot=True)

        tmp_dict = self.map_offset_to_statsmodels_dict[0]
        statsmodels_model_deceased = tmp_dict['statsmodels_model_deceased']
        statsmodels_model_positive = tmp_dict['statsmodels_model_positive']
        statsmodels_params = tmp_dict['statsmodels_params']
        statsmodels_bse = tmp_dict['statsmodels_bse']

        tmp_dict = self.map_offset_to_statsmodels_dict[7]
        statsmodels_model_deceased_one_week_ago = tmp_dict['statsmodels_model_deceased']
        statsmodels_model_positive_one_week_ago = tmp_dict['statsmodels_model_positive']
        statsmodels_params_one_week_ago = tmp_dict['statsmodels_params']
        statsmodels_bse_one_week_ago = tmp_dict['statsmodels_bse']
        # print('statsmodels_params:', statsmodels_params)
        # print('statsmodels_params_one_week_ago:', statsmodels_params_one_week_ago)

        map_param_to_acc = dict()
        for param in statsmodels_params:
            bse_one = statsmodels_bse_one_week_ago[param]
            bse_two = statsmodels_bse[param]
            slope_one = statsmodels_params_one_week_ago[param]
            slope_two = statsmodels_params[param]
            z_score = (slope_two - slope_one) / np.sqrt(bse_one ** 2 + bse_two ** 2)
            p_value = sp.stats.norm.sf(abs(z_score))
            print(f'{param}:')
            print(f'  bse_one: {bse_one:.4g} slope_one: {slope_one:.4g}')
            print(f'  bse_two: {bse_two:.4g} slope_two: {slope_two:.4g}')
            print(f'  z_score: {z_score:.4g} p_value: {p_value:.4g}')

            tmp_dict = {
                'bse1': bse_one,
                'bse2': bse_two,
                'slope1': slope_one,
                'slope2': slope_two,
                'z_score': z_score,
                'p_value': p_value,
                'offset': offset
            }
            map_param_to_acc[param] = tmp_dict

        self.map_param_to_acc = map_param_to_acc

    def _render_statsmodels_fit_sub(self, opt_simplified=False, offset=0, opt_plot=True, opt_print=True):
        '''
        Performs fit using statsmodels, since this is a standard linear regression. This model gives us standard errors.
        :return: 
        '''

        # this only needs to be imported if it's being used...
        import statsmodels.formula.api as smf

        name_mapping_positive = {'DOW[T.1]': 'day1_positive_multiplier',
                                 'DOW[T.2]': 'day2_positive_multiplier',
                                 'DOW[T.3]': 'day3_positive_multiplier',
                                 'DOW[T.4]': 'day4_positive_multiplier',
                                 'DOW[T.5]': 'day5_positive_multiplier',
                                 'DOW[T.6]': 'day6_positive_multiplier',
                                 'x': 'positive_slope',
                                 'Intercept': 'positive_intercept'
                                 }

        name_mapping_deceased = {'DOW[T.1]': 'day1_deceased_multiplier',
                                 'DOW[T.2]': 'day2_deceased_multiplier',
                                 'DOW[T.3]': 'day3_deceased_multiplier',
                                 'DOW[T.4]': 'day4_deceased_multiplier',
                                 'DOW[T.5]': 'day5_deceased_multiplier',
                                 'DOW[T.6]': 'day6_deceased_multiplier',
                                 'x': 'deceased_slope',
                                 'Intercept': 'deceased_intercept'
                                 }

        positive_names = [name for name in self.sorted_names if 'positive' in name and 'sigma' not in name]
        deceased_names = [name for name in self.sorted_names if 'deceased' in name and 'sigma' not in name]
        map_positive_names_to_sorted_ind = {val: ind for ind, val in enumerate(positive_names)}
        map_deceased_names_to_sorted_ind = {val: ind for ind, val in enumerate(deceased_names)}

        data_new_tested = self.data_new_tested
        data_new_deceased = self.data_new_dead
        moving_window_size = self.moving_window_size
        cases_bootstrap_indices = self.cases_indices[-moving_window_size:]
        deaths_bootstrap_indices = self.deaths_indices[-moving_window_size:]

        # print('len(data_new_tested):', len(data_new_tested))
        # print('len(data_new_deceased):', len(data_new_deceased))

        # print('series_data:',  self.series_data)
        data = pd.DataFrame([{'x': ind,
                              # add burn_in to orig_ind since simulations start earlier than the data
                              'orig_ind': i + self.burn_in,
                              'new_positive': data_new_tested[i] + self.log_offset,
                              'new_deceased': data_new_deceased[i] + self.log_offset,
                              } for ind, i in
                             enumerate(range(len(data_new_tested) - moving_window_size - offset,
                                             len(data_new_tested) - offset))])

        # need to use orig_ind to align intercept with run_simulation
        ind_offset = 0  # had to hand-tune this to zero
        data['DOW'] = [str((x + ind_offset) % 7) for x in data['orig_ind']]
        data['log_offset'] = self.log_offset

        #####
        # Do fit on positive curve
        #####

        model_positive = smf.ols(formula='np.log(new_positive) ~ x + DOW',
                                 data=data)  # add 0.1 to avoid log(0)
        results_positive = model_positive.fit()
        if opt_print:
            print(results_positive.summary())
        params_positive = dict(results_positive.params)
        for name1, name2 in name_mapping_positive.items():
            params_positive[name2] = params_positive.pop(name1)
        # params_positive['positive_intercept'] = np.exp(params_positive['positive_intercept'])
        bse_positive = dict(results_positive.bse)
        for name1, name2 in name_mapping_positive.items():
            bse_positive[name2] = bse_positive.pop(name1)
        # bse_positive['positive_intercept'] = bse_positive['positive_intercept'] * \
        #    params_positive['positive_intercept']  # due to A = 1000; B = 0.01; B * np.exp(A) = np.exp(A + B) - np.exp(A)
        # also, note that we have already applied hte exponential transofrm on A
        means_as_list = [params_positive[name] for name in positive_names]
        sigma_as_list = [bse_positive[name] for name in positive_names]

        # print('Statsmodels results for positive:')
        # print('sigma_as_list:', sigma_as_list)
        # print('means_as_list:', means_as_list)

        # cov = np.diag([max(1e-8, x ** 2) for x in sigma_as_list])
        cov = results_positive.cov_params()
        # print('Cov columns:', cov.columns)

        # get ordering of rows and cols correct
        mapping_list = [map_positive_names_to_sorted_ind[name_mapping_positive[col]] for col in cov.columns]
        inv_mapping_list = [mapping_list.index(i) for i in range(len(mapping_list))]
        cov = cov.values
        cov = cov[inv_mapping_list, :]
        cov = cov[:, inv_mapping_list]

        # render corr
        # corr = self.cov2corr(cov)
        # print('diag(cov:)')
        # print(np.diagonal(cov))
        # print('corr:')
        # print(corr)

        statsmodels_model_positive = sp.stats.multivariate_normal(mean=means_as_list, cov=cov)

        #####
        # Do fit on deceased curve
        #####

        # add 0.1 so you don't bonk on log(0)
        model_deceased = smf.ols(formula='np.log(new_deceased) ~ x + DOW',
                                 data=data)  # add 0.1 to avoid log(0)
        results_deceased = model_deceased.fit()
        if opt_print:
            print(results_deceased.summary())
        params_deceased = dict(results_deceased.params)
        for name1, name2 in name_mapping_deceased.items():
            params_deceased[name2] = params_deceased.pop(name1)
        # params_deceased['deceased_intercept'] = np.exp(params_deceased['deceased_intercept'])
        means_as_list = [params_deceased[name] for name in deceased_names]
        bse_deceased = dict(results_deceased.bse)
        for name1, name2 in name_mapping_deceased.items():
            bse_deceased[name2] = bse_deceased.pop(name1)
        # bse_deceased['deceased_intercept'] = bse_deceased['deceased_intercept'] * \
        #     params_deceased['deceased_intercept']  # due to A = 1000; B = 0.01; B * np.exp(A) = np.exp(A + B) - np.exp(A)
        # also, note that we have already applied hte exponential transofrm on A
        # print(bse_deceased)
        sigma_as_list = [bse_deceased[name] for name in deceased_names]

        # print('Statsmodels results for deceased:')
        # print('sigma_as_list:', sigma_as_list)
        # print('means_as_list:', means_as_list)

        # cov = np.diag([max(1e-8, x ** 2) for x in sigma_as_list])
        cov = results_deceased.cov_params()

        # get ordering of rows and cols correct
        mapping_list = [map_deceased_names_to_sorted_ind[name_mapping_deceased[col]] for col in cov.columns]
        inv_mapping_list = [mapping_list.index(i) for i in range(len(mapping_list))]
        cov = cov.values
        cov = cov[inv_mapping_list, :]
        cov = cov[:, inv_mapping_list]

        # render corr
        # corr = self.cov2corr(cov)
        # print('cov:')
        # print(cov)
        # print('corr:')
        # print(corr)

        tmp_params = params_positive.copy()
        tmp_params.update(params_deceased)
        for param_name in self.logarithmic_params:
            if 'sigma' in param_name:
                continue
            tmp_params[param_name] = np.exp(tmp_params.pop(param_name))
        statsmodels_params = tmp_params

        tmp_bse = bse_positive.copy()
        tmp_bse.update(bse_deceased)
        for param_name in self.logarithmic_params:
            if 'sigma' in param_name:
                continue
            tmp_bse[param_name] = np.exp(tmp_bse.pop(param_name))
        statsmodels_bse = tmp_bse

        statsmodels_model_deceased = sp.stats.multivariate_normal(mean=means_as_list, cov=cov)
        self.statsmodels_model_deceased = statsmodels_model_deceased
        self.statsmodels_model_positive = statsmodels_model_positive
        self.statsmodels_params = statsmodels_params
        self.statsmodels_bse = statsmodels_bse

        if not hasattr(self, 'map_offset_to_statsmodels_dict'):
            self.map_offset_to_statsmodels_dict = dict()
        self.map_offset_to_statsmodels_dict[offset] = {
            'statsmodels_model_deceased': statsmodels_model_deceased,
            'statsmodels_model_positive': statsmodels_model_positive,
            'statsmodels_params': statsmodels_params,
            'statsmodels_bse': statsmodels_bse,
        }

        if opt_plot:
            if not opt_simplified:
                self.render_and_plot_cred_int(approx_type=ApproxType.SM)
            self.plot_all_solutions(approx_type=ApproxType.SM, offset=offset)

    def get_weighted_samples_via_PyMC3(self, n_samples=1000, ):

        samples = self.all_PyMC3_samples_as_list
        log_probs = self.all_PyMC3_log_probs_as_list
        samples = [self.convert_params_as_dict_to_list(sample) for sample in samples]

        sampled_ind = np.random.choice(len(samples), n_samples)
        samples = [samples[i] for i in sampled_ind]
        log_probs = [log_probs[i] for i in sampled_ind]

        return samples, samples, [1] * len(samples), log_probs

    def get_weighted_samples_via_statsmodels(self, n_samples=1000):
        '''
        Retrieves likelihood samples in parameter space, weighted by their standard errors from statsmodels
        :param n_samples: how many samples to re-sample from the list of likelihood samples
        :return: tuple of weight_sampled_params, params, weights, log_probs
        '''

        weight_sampled_params_positive = self.statsmodels_model_positive.rvs(n_samples)
        weight_sampled_params_deceased = self.statsmodels_model_deceased.rvs(n_samples)

        positive_names = [name for name in self.sorted_names if 'positive' in name and 'sigma' not in name]
        map_name_to_sorted_ind_positive = {val: i for i, val in enumerate(positive_names)}
        deceased_names = [name for name in self.sorted_names if 'deceased' in name and 'sigma' not in name]
        map_name_to_sorted_ind_deceased = {val: i for i, val in enumerate(deceased_names)}

        weight_sampled_params = list()
        for i in range(n_samples):
            positive_dict = self.convert_params_as_list_to_dict(weight_sampled_params_positive[i],
                                                                map_name_to_sorted_ind=map_name_to_sorted_ind_positive)
            deceased_dict = self.convert_params_as_list_to_dict(weight_sampled_params_deceased[i],
                                                                map_name_to_sorted_ind=map_name_to_sorted_ind_deceased)
            all_dict = positive_dict.copy()
            all_dict.update(deceased_dict)
            all_dict['sigma_positive'] = 1
            all_dict['sigma_deceased'] = 1
            for name in self.logarithmic_params:
                all_dict[name] = np.exp(all_dict[name])
            weight_sampled_params.append(self.convert_params_as_dict_to_list(all_dict.copy()))

        log_probs = [self.get_log_likelihood(x) for x in weight_sampled_params]

        return weight_sampled_params, weight_sampled_params, [1] * len(weight_sampled_params), log_probs

    def run_fits_simplified(self):
        '''
        Builder that goes through each method in its proper sequence
        :return: None
        '''

        if ApproxType.SM in self.model_approx_types:
            self.render_statsmodels_fit_timeseries(opt_simplified=True)
            self.plot_growth_rate_timeseries(plot_filename_filename='statsmodels_growth_rate_time_series.png')
            self.render_statsmodels_fit(opt_simplified=True)
            self.fit_MVN_to_likelihood(cov_type='full', approx_type=ApproxType.SM)

        if ApproxType.PyMC3 in self.model_approx_types:
            self.render_PyMC3_fit(opt_simplified=True)
            self.fit_MVN_to_likelihood(cov_type='full', approx_type=ApproxType.PyMC3)

    def plot_growth_rate_timeseries(self,
                                    plot_filename_filename=None,
                                    data_plot_kwargs=dict()):
        '''
        Helper function to plot_all_solutions
        :param plot_filename_filename: string to add to the plot filename
        :return: None
        '''

        full_output_filename = path.join(self.plot_filename_base, plot_filename_filename)
        if path.exists(full_output_filename) and not self.opt_force_plot:
            print(f'{full_output_filename} already exists, skipping plot.')
            return
        
        plt.close()
        plt.clf()
        fig, ax = plt.subplots()
        plt.axhline(linestyle='--', y=0, color='black')

        map_t_val_ind_to_tested_distro = dict()
        map_t_val_ind_to_deceased_distro = dict()

        use_min_date = self.min_date + datetime.timedelta(days=self.day_of_threshold_met_case)
        use_max_date = self.max_date
        timeseries_length_in_days = (use_max_date - use_min_date).days
        for offset in range(timeseries_length_in_days):
            t_val = self.max_date - datetime.timedelta(days=offset)
            bse = self.map_offset_to_statsmodels_dict[offset]['statsmodels_bse']
            bse['sigma_positive'] = 0.1
            bse['sigma_deceased'] = 0.1
            sigmas_as_list = self.convert_params_as_dict_to_list(bse)
            params = self.map_offset_to_statsmodels_dict[offset]['statsmodels_params']
            params['sigma_positive'] = 0.1
            params['sigma_deceased'] = 0.1
            means_as_list = self.convert_params_as_dict_to_list(params)
            cov = np.diag([max(1e-8, x ** 2) for x in sigmas_as_list])
            model = sp.stats.multivariate_normal(mean=means_as_list, cov=cov)
            map_t_val_ind_to_tested_distro[t_val] = model.rvs(1000)[:, self.map_name_to_sorted_ind['positive_slope']]
            map_t_val_ind_to_deceased_distro[t_val] = model.rvs(1000)[:, self.map_name_to_sorted_ind['deceased_slope']]

        sol_plot_date_range = sorted(map_t_val_ind_to_tested_distro.keys())
        p5_curve = [np.percentile(map_t_val_ind_to_deceased_distro[val_ind], 5) for val_ind in sol_plot_date_range]
        p25_curve = [np.percentile(map_t_val_ind_to_deceased_distro[val_ind], 25) for val_ind in
                     sol_plot_date_range]
        p50_curve = [np.percentile(map_t_val_ind_to_deceased_distro[val_ind], 50) for val_ind in
                     sol_plot_date_range]
        p75_curve = [np.percentile(map_t_val_ind_to_deceased_distro[val_ind], 75) for val_ind in
                     sol_plot_date_range]
        p95_curve = [np.percentile(map_t_val_ind_to_deceased_distro[val_ind], 95) for val_ind in
                     sol_plot_date_range]

        ax.fill_between(sol_plot_date_range,
                        p5_curve,
                        p95_curve,
                        facecolor=matplotlib.colors.colorConverter.to_rgba('red', alpha=0.3),
                        edgecolor=(0, 0, 0, 0)  # get rid of the darker edge
                        )
        ax.fill_between(sol_plot_date_range,
                        p25_curve,
                        p75_curve,
                        facecolor=matplotlib.colors.colorConverter.to_rgba('red', alpha=0.6),
                        edgecolor=(0, 0, 0, 0)  # r=get rid of the darker edge
                        )
        ax.plot(sol_plot_date_range, p50_curve,
                color="darkred", label='Deaths')

        p5_curve = [np.percentile(map_t_val_ind_to_tested_distro[val_ind], 5) for val_ind in sol_plot_date_range]
        p25_curve = [np.percentile(map_t_val_ind_to_tested_distro[val_ind], 25) for val_ind in
                     sol_plot_date_range]
        p50_curve = [np.percentile(map_t_val_ind_to_tested_distro[val_ind], 50) for val_ind in
                     sol_plot_date_range]
        p75_curve = [np.percentile(map_t_val_ind_to_tested_distro[val_ind], 75) for val_ind in
                     sol_plot_date_range]
        p95_curve = [np.percentile(map_t_val_ind_to_tested_distro[val_ind], 95) for val_ind in
                     sol_plot_date_range]

        ax.fill_between(sol_plot_date_range,
                        p5_curve,
                        p95_curve,
                        facecolor=matplotlib.colors.colorConverter.to_rgba('green', alpha=0.3),
                        edgecolor=(0, 0, 0, 0)  # get rid of the darker edge
                        )
        ax.fill_between(sol_plot_date_range,
                        p25_curve,
                        p75_curve,
                        facecolor=matplotlib.colors.colorConverter.to_rgba('green', alpha=0.6),
                        edgecolor=(0, 0, 0, 0)  # get rid of the darker edge
                        )
        ax.plot(sol_plot_date_range, p50_curve,
                color="darkgreen", label='Infections')

        fig.autofmt_xdate()

        # this removes the year from the x-axis ticks
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))

        # ax.fmt_xdata = mdates.DateFormatter('%Y-%m-%d')
        plt.ylabel('Daily Growth Rate')
        # plt.ylim((1, sum(self.data_new_tested) * 100))
        plt.xlim(min(map_t_val_ind_to_tested_distro.keys()), max(map_t_val_ind_to_tested_distro.keys()) + datetime.timedelta(days=5))
        plt.legend()
        # plt.title(f'{state} Data (points) and Model Predictions (lines)')
        print(f'Printing {full_output_filename}...')
        plt.savefig(full_output_filename, dpi=self.plot_dpi)
        plt.close()
        print('...done!')

    def render_PyMC3_fit(self, opt_simplified=False):

        success = False
        print(f'Loading from {self.PyMC3_filename}...')
        try:
            PyMC3_dict = joblib.load(self.PyMC3_filename)
            all_PyMC3_samples_as_list = PyMC3_dict['all_PyMC3_samples_as_list']
            all_PyMC3_log_probs_as_list = PyMC3_dict['all_PyMC3_log_probs_as_list']
            success = True
            self.loaded_PyMC3 = True
        except:
            print('...Loading failed!')
            self.loaded_PyMC3 = False

        # TODO: Break out all-data fit to its own method, not embedded in render_bootstraps
        if (not success and self.opt_calc) or self.opt_force_calc:

            print('Massaging data into dataframe...')

            # PyMC3 requires a Pandas dataframe, so let's get cooking!
            data_as_list_of_dicts = [{'new_tested': self.data_new_tested[i],
                                      'new_dead': self.data_new_dead[i],
                                      'log_new_tested': np.log(self.data_new_tested[i] + self.log_offset),
                                      'log_new_dead': np.log(self.data_new_dead[i] + self.log_offset),
                                      'orig_ind': i + self.burn_in,
                                      'x': ind,
                                      } for ind, i in enumerate(
                range(len(self.data_new_tested) - self.moving_window_size, len(self.data_new_tested)))]

            data = pd.DataFrame(data_as_list_of_dicts)

            ind_offset = 0  # had to hand-tune this to zero
            data['DOW'] = [str((x + ind_offset) % 7) for x in data['orig_ind']]
            data['day1'] = [1 if (x + ind_offset) % 7 == 1 else 0 for x in data['orig_ind']]
            data['day2'] = [1 if (x + ind_offset) % 7 == 2 else 0 for x in data['orig_ind']]
            data['day3'] = [1 if (x + ind_offset) % 7 == 3 else 0 for x in data['orig_ind']]
            data['day4'] = [1 if (x + ind_offset) % 7 == 4 else 0 for x in data['orig_ind']]
            data['day5'] = [1 if (x + ind_offset) % 7 == 5 else 0 for x in data['orig_ind']]
            data['day6'] = [1 if (x + ind_offset) % 7 == 6 else 0 for x in data['orig_ind']]

            print('Running PyMC3 fit...')
            with pm.Model() as model_positive:  # model specifications in PyMC3 are wrapped in a with-statement

                # Define priors
                intercept = pm.Normal('positive_intercept', 10, sigma=5)
                x_coeff = pm.Normal('positive_slope', 0, sigma=0.5)
                sigma = pm.HalfNormal('sigma_positive', sigma=1)

                day1_mult = pm.Normal('day1_positive_multiplier', 0, sigma=0.5)
                day2_mult = pm.Normal('day2_positive_multiplier', 0, sigma=0.5)
                day3_mult = pm.Normal('day3_positive_multiplier', 0, sigma=0.5)
                day4_mult = pm.Normal('day4_positive_multiplier', 0, sigma=0.5)
                day5_mult = pm.Normal('day5_positive_multiplier', 0, sigma=0.5)
                day6_mult = pm.Normal('day6_positive_multiplier', 0, sigma=0.5)

                # Define likelihood
                Y_obs = pm.Normal('new_tested', mu=intercept + x_coeff * data['x'] + \
                                                   day1_mult * data['day1'] + \
                                                   day2_mult * data['day2'] + \
                                                   day3_mult * data['day3'] + \
                                                   day4_mult * data['day4'] + \
                                                   day5_mult * data['day5'] + \
                                                   day6_mult * data['day6'],
                                  sigma=sigma,  # 1/np.exp(data_log['y']),
                                  observed=data['log_new_tested'])

                # Inference!
                print("Searching for MAP...")
                MAP = pm.find_MAP(model=model_positive)
                print('...done! MAP:')
                print(MAP)
                positive_trace = pm.sample(2000, start=MAP)

            positive_trace_as_dict = {name: positive_trace.get_values(name) for name in self.sorted_names if
                                      'positive' in name}
            positive_trace_as_list_of_dicts = list()
            for i in range(len(positive_trace.get_values('positive_slope'))):
                dict_to_add = dict()
                for name in positive_trace_as_dict:
                    dict_to_add.update({name: positive_trace_as_dict[name][i]})
                positive_trace_as_list_of_dicts.append(dict_to_add)

            with pm.Model() as model_deceased:  # model specifications in PyMC3 are wrapped in a with-statement

                # Define priors
                intercept = pm.Normal('deceased_intercept', 10, sigma=5)
                x_coeff = pm.Normal('deceased_slope', 0, sigma=0.5)
                sigma = pm.HalfNormal('sigma_deceased', sigma=1)

                day1_mult = pm.Normal('day1_deceased_multiplier', 0, sigma=0.5)
                day2_mult = pm.Normal('day2_deceased_multiplier', 0, sigma=0.5)
                day3_mult = pm.Normal('day3_deceased_multiplier', 0, sigma=0.5)
                day4_mult = pm.Normal('day4_deceased_multiplier', 0, sigma=0.5)
                day5_mult = pm.Normal('day5_deceased_multiplier', 0, sigma=0.5)
                day6_mult = pm.Normal('day6_deceased_multiplier', 0, sigma=0.5)

                # Define likelihood
                Y_obs = pm.Normal('new_dead', mu=intercept + x_coeff * data['x'] + \
                                                 day1_mult * data['day1'] + \
                                                 day2_mult * data['day2'] + \
                                                 day3_mult * data['day3'] + \
                                                 day4_mult * data['day4'] + \
                                                 day5_mult * data['day5'] + \
                                                 day6_mult * data['day6'],
                                  sigma=sigma,  # 1/np.exp(data_log['y']),
                                  observed=data['log_new_dead'])

                # Inference!
                print("Searching for MAP...")
                MAP = pm.find_MAP(model=model_deceased)
                print('...done! MAP:')
                print(MAP)
                deceased_trace = pm.sample(2000, start=MAP)

            deceased_trace_as_dict = {name: deceased_trace.get_values(name) for name in self.sorted_names if
                                      'deceased' in name}
            deceased_trace_as_list_of_dicts = list()
            for i in range(len(deceased_trace.get_values('deceased_slope'))):
                dict_to_add = dict()
                for name in deceased_trace_as_dict:
                    dict_to_add.update({name: deceased_trace_as_dict[name][i]})
                deceased_trace_as_list_of_dicts.append(dict_to_add)

            trace_as_list_of_dicts = list()
            for positive_params, deceased_params in zip(positive_trace_as_list_of_dicts,
                                                        deceased_trace_as_list_of_dicts):
                dict_to_add = positive_params.copy()
                dict_to_add.update(deceased_params)
                trace_as_list_of_dicts.append(dict_to_add)

            for tmp_dict in trace_as_list_of_dicts:
                for key in tmp_dict:
                    if key in self.logarithmic_params:
                        tmp_dict[key] = np.exp(tmp_dict[key])

            all_PyMC3_samples_as_list = [self.convert_params_as_dict_to_list(tmp_dict) for tmp_dict in
                                         trace_as_list_of_dicts]
            all_PyMC3_log_probs_as_list = [self.get_log_likelihood(params) for params in trace_as_list_of_dicts]

            tmp_dict = {'all_PyMC3_samples_as_list': all_PyMC3_samples_as_list,
                        'all_PyMC3_log_probs_as_list': all_PyMC3_log_probs_as_list}

            print(f'saving PyMC3 trace to {self.PyMC3_filename}...')
            joblib.dump(tmp_dict, self.PyMC3_filename)
            print('...done!')

        self.all_PyMC3_samples_as_list = all_PyMC3_samples_as_list
        self.all_PyMC3_log_probs_as_list = all_PyMC3_log_probs_as_list

        # Plot all solutions...
        self.plot_all_solutions(approx_type=ApproxType.PyMC3)

        if not opt_simplified:
            # Get and plot parameter distributions from bootstraps
            self.render_and_plot_cred_int(approx_type=ApproxType.PyMC3)
