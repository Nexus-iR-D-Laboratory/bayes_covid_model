import sub_units.load_data as load_data
from sub_units.utils import generate_plot_browser as generate_plot_browser_imported

#####
# Setup
#####
base_url_dir = 'https://covid-figures.s3-us-west-2.amazonaws.com/'
hyperparameter_str = '2020_05_13_date_smoothed_moving_window_21_days_statsmodels_only'
github_url = 'https://github.com/douglasmason/covid_model'
plot_browser_dir = 'plot_browser_moving_window_statsmodels_only'
full_report_filename = 'full_us_report.html'

list_of_figures = [
    #'statsmodels_param_distro_without_priors.png',
    'statsmodels_solutions_discrete.png',
    'statsmodels_solutions_filled_quantiles.png',
    'statsmodels_solutions_cumulative_discrete.png',
    'statsmodels_solutions_cumulative_filled_quantiles.png',
]

list_of_figures_full_report = [
    'simplified_boxplot_for_positive_slope_statsmodels.png',
    'simplified_boxplot_for_deceased_slope_statsmodels.png'
]

#####
# Execute
#####

def generate_plot_browser():
    
    full_url_dir = base_url_dir + hyperparameter_str
    
    generate_plot_browser_imported(plot_browser_dir, 
                                   load_data, 
                                   full_url_dir, 
                                   github_url, 
                                   full_report_filename, 
                                   list_of_figures, 
                                   list_of_figures_full_report)

if __name__ == '__main__':
    generate_plot_browser