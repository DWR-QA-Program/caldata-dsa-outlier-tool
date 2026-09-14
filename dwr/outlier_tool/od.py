# Outlier detection functions and functions related to using outlier detection tests.
#
# NOTE: The app calls outlier detection functions using the **kwargs construct.
#       Due to this, changing the names of these functions arguments also requires
#       changing values in the OD_IMPLEMENTED dictionary.

import asyncio
import time

import pandas as pd
from shiny import ui

from . import app_state, m, od_core
from .m import _F, MANUAL, MULTIPLE_FAILURES, PASS

OD_IMPLEMENTED = {
    # Dictionary structure:
    # 'unique_test_name': {
    #     'fn': function_that_runs_outlier_dection,
    #     'plain': 'plain test name'
    #     'desc': one-line description for the checkbox tooltip on the Test tab.
    #     'help': longer explanation shown at the top of the test's accordion
    #             panel. Omit for tests with no arguments.
    #     'group': which card the test appears under on the Test tab. One of
    #              'value', 'sequential', or 'comparison' (see text.TEST_GROUP_INFO).
    #     'args': list of tuples (if omitted, the test needs no arguments) (
    #               ('internal arg name', 'Display argument name', 'data type',
    #                'default value', 'optional help text shown under the input')
    #             )
    #     'ts_col_type': One of 'x', 'y', or 'xy' to let the tool know what columns
    #                    to allow test execution on.
    #     'col_widths': optional configuration to pass to accordion creation, affects argument layout
    #                   and can be used to limit the overall size of input boxes inside the accordion.
    # }
'gross_range_test': {
        'fn': od_core.gross_range_test,
        'plain': 'Gross range test',
        'desc': 'Flags values outside a set min/max range.',
        'help': (
            'Compares each value with the specified minimum and maximum limits. '
            'Values outside those limits are flagged; values exactly on the limits pass.'
        ),
        'group': 'value',
        'ts_col_type': 'y',
        'args': (
            ('minimum', 'Min', float, None, 'Lower bound.'),
            ('maximum', 'Max', float, None, 'Upper bound.'),
        ),
        'col_widths': (6, 6),  # this affects input sizes in accordions
    },
    'time_gap_test': {
        'fn': od_core.time_gap_test,
        'plain': 'Time gap test',
        'desc': 'Flags gaps in the expected reporting cadence.',
        'help': (
            'Compares the time between consecutive readings with the expected interval. '
            'Longer intervals are flagged as gaps.'
        ),
        'group': 'sequential',
        'ts_col_type': 'x',
        'args': (
            ('number', 'Interval Length', int, None, 'How long between expected readings.'),
            ('unit', 'Unit', 'date_unit', None, 'Time unit for the interval.'),
        ),
        'col_widths': (6, 6),
    },
    'value_gap_test': {
        'fn': od_core.value_gap_test,
        'plain': 'Value gap test',
        'desc': 'Flags missing values. No setup needed.',
        'help': ('Checks whether an analyte value is missing. Missing values are flagged.'),
        'group': 'value',
        'ts_col_type': 'xy',
    },
    'flat_line_test': {
        'fn': od_core.flat_line_test,
        'plain': 'Flat line test',
        'desc': 'Flags values that repeat too many times in a row.',
        'help': (
            'Looks for consecutive runs of identical readings. '
            'Once a run reaches the selected length, the entire run is flagged; '
            'missing values are not treated as repeated readings.'
        ),
        'group': 'sequential',
        'ts_col_type': 'xy',
        'args': (
            (
                'number_of_repeated_values',
                'Repeated Values',
                int,
                None,
                'How many identical readings in a row before the run is flagged.',
            ),
        ),
        'col_widths': (6,),
    },
    'z_score_test': {
        'fn': od_core.z_score_test,
        'plain': 'Z-score test',
        'desc': 'Flags values far from the mean. Sensitive to extremes.',
        'help': (
            'Measures how far each value is from the mean in standard deviations. '
            'Values beyond the selected number of standard deviations are flagged.'
        ),
        'group': 'comparison',
        'ts_col_type': 'y',
        'args': (
            (
                'number_of_standard_deviations',
                'Standard Deviations',
                int,
                3,
                'Points beyond this many deviations are flagged. 3 is typical.',
            ),
        ),
        'col_widths': (6,),
    },
    'modified_z_score_test': {
        'fn': od_core.modified_z_score_test,
        'plain': 'Modified z-score test',
        'desc': 'Flags outliers using the median. Robust to extreme values.',
        'help': (
                'Measures how far each value is from the median using a robust measure of spread. '
                'Values beyond the selected modified z-score cutoff are flagged.'
        ),
        'group': 'value',
        'ts_col_type': 'y',
        'args': (
            (
                'median_absolute_deviation',
                'Modified Z-score Threshold',
                float,
                3.5,
                'Values above this threshold are flagged. 3.5 is typical.',
            ),
        ),
        'col_widths': (6,),
    },
    'tukey_iqr_test': {
        'fn': od_core.tukey_iqr_test,
        'plain': 'Tukey IQR test',
        'desc': 'Flags values far outside the middle 50%. No setup needed.',
        'help': (
            'Uses the middle 50% of the data to define the typical spread. '
            'Values sufficiently far below or above that range are flagged.'
        ),
        'group': 'value',
        'ts_col_type': 'y',
    },
    'spike_detection_test': {
        'fn': od_core.spike_detection_test,
        'plain': 'Local median',
        'desc': 'Flags isolated points that differ sharply from nearby readings.',
        'help': (
            'Compares each reading with the median of nearby readings on both sides. '
            'Values that differ from that local median by at least the selected percentage are flagged.'
        ),
        'group': 'sequential',
        'ts_col_type': 'y',
        'args': (
            (
                'percent_difference',
                'Percent Difference',
                float,
                20,
                'Minimum percent difference from nearby readings required to flag a point.',
            ),
            (
                'nearby_readings',
                'Nearby Readings',
                int,
                3,
                'Number of readings on each side used to calculate the local median.',
            ),
        ),
        'col_widths': (6, 6),
    },
    'rate_of_change_test': {
        'fn': od_core.rate_of_change_test,
        'plain': 'Local level comparison',
        'desc': 'Flags abrupt shifts in the local level of the data.',
        'help': (
            'Compares the median of readings before and after a potential change. '
            'A shift is flagged when those local levels differ by at least the selected percentage.'
        ),
        'group': 'sequential',
        'ts_col_type': 'y',
        'args': (
            (
                'percent_change',
                'Percent Change',
                float,
                20,
                'Minimum percent change between the before and after local levels required to flag a change.',
            ),
            (
                'nearby_readings',
                'Nearby Readings',
                int,
                3,
                'Number of readings used on each side of the potential change.',
            ),
        ),
        'col_widths': (6, 6),
    },
}

def apply_renames(figure, renames) -> None:
    if renames:
        figure.for_each_trace(
            lambda x: x.update(
                name=renames[x.name],
                legendgroup=renames[x.name],
                hovertemplate=x.hovertemplate.replace(x.name, renames[x.name]),
            )
        )


# Returns list of default tests we can run on any dataset
def get_default_tests(file: app_state.File):
    raise NotImplementedError('needs to account for not using x column')
    test_types = {
        'x': [time_gap_test_auto],
        'y': [od_core.value_gap_test],
    }

    ret = []
    for date_test in test_types['x']:
        ret.extend((date_test, x_col, None, {}) for x_col in file.date_cols)
    for value_test in test_types['y']:
        ret.extend((value_test, x_col, y_col, {}) for x_col in file.date_cols for y_col in file.num_cols)
    return ret


def time_gap_test_auto(ts: pd.Series) -> pd.Series:
    return od_core.time_gap_test(ts, None, None, ts.diff().median())


async def run_od(test_list, file_obj: app_state.File):
    n_tests = len(test_list)

    with ui.Progress(min=0, max=n_tests) as p:
        for i, (test_key, analyte, test_col, kwargs) in enumerate(test_list):
            test_fn = OD_IMPLEMENTED[test_key]['fn']

            msg = f'({i + 1}/{n_tests})'
            p.set(i, message=msg, detail=OD_IMPLEMENTED[test_key]['plain'])

            # Resolve the analyte down to a series. In wide format this is just
            # df[test_col]; in long format it's test_col restricted to the rows
            # belonging to this analyte. Either way the test itself is unchanged.
            series = file_obj.get_series(analyte, test_col)

            start_time = time.perf_counter()
            try:
                result = test_fn(series, **kwargs)
            except Exception as e:
                file_obj.save_od_result(analyte, test_key, error=repr(e))
            else:
                file_obj.save_od_result(analyte, test_key, result=result, params=dict(kwargs))

            # When tests execute quickly, add a delay so that the progress bar is visible
            sleep_duration = m.MIN_DUR if time.perf_counter() - start_time < m.MIN_DUR else 0

            # Free up the event loop to switch tasks so that the UI can respond
            # to events while tests are running.
            await asyncio.sleep(sleep_duration)

OD_TESTS = {
    'plausible_limits': {
        'label': 'Plausible limits',
        'color': '#1b9e77',
        'desc': 'Find values outside limits you choose.',
        'group': 'value',
        'methods': ('gross_range_test',),
        'method_mode': 'single',
    },
    'extreme_values': {
        'label': 'Extreme values',
        'color': '#d95f02',
        'desc': 'Find unusually high or low values compared with the rest of the data.',
        'help': 'Choose the statistical method used to identify extreme values.',
        'group': 'value',
        'methods': (
            'z_score_test',
            'modified_z_score_test',
            'tukey_iqr_test',
        ),
        'method_mode': 'choose_one',
        'method_choices': {
            'z_score_test': 'Z-score',
            'modified_z_score_test': 'Modified z-score',
            'tukey_iqr_test': 'IQR',
        },
    },
    'missing_data': {
        'label': 'Missing data',
        'color': '#7570b3',
        'desc': 'Find missing values or data gaps.',
        'help': (
            'Checks for both missing analyte values and gaps between expected readings. '
            'Missing values are flagged directly, '
            'and time gaps are flagged when the interval between readings is longer than expected.'
        ),
        'group': 'sequential',
        'methods': (
            'time_gap_test',
            'value_gap_test',
        ),
        'method_mode': 'all',
        'method_label': 'Time/value gap test',
        'needs_date': True,
    },
    'stuck_values': {
        'label': 'Stuck values',
        'color': '#e7298a',
        'desc': 'Find values that repeat too many times in a row.',
        'group': 'sequential',
        'methods': ('flat_line_test',),
        'method_mode': 'single',
    },
    'spike_detection': {
        'label': 'Sudden data spikes',
        'color': '#66a61e',
        'desc': 'Find isolated points that differ sharply from nearby readings.',
        'help': (
            'Looks for individual readings that depart from the local pattern '
            'but then return to it.'
        ),
        'group': 'sequential',
        'methods': ('spike_detection_test',),
        'method_mode': 'single',
    },
    'rate_of_change': {
        'label': 'Sudden changes',
        'color': '#e6ab02',
        'desc': 'Find abrupt shifts in the local level of the data.',
        'help': (
            'Looks for changes that persist across several readings rather than '
            'a single isolated spike.'
        ),
        'group': 'sequential',
        'methods': ('rate_of_change_test',),
        'method_mode': 'single',
    },
}