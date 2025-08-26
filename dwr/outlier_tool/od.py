# Outlier detection functions and functions related to using outlier detection tests.
#
# NOTE: The app calls outlier detection functions using the **kwargs construct.
#       Due to this, changing the names of these functions arguments also requires
#       changing values in the OD_IMPLEMENTED dictionary.

import pandas as pd

from . import app_state, od_core
from .m import _F, MANUAL, MULTIPLE_FAILURES, PASS

OD_IMPLEMENTED = {
    'gross_range_test': {
        'fn': od_core.gross_range_test,
        'plain': 'Gross range test',
        'ts_col_type': 'y',
        'args': (
            ('minimum', 'Min', float, None),
            ('maximum', 'Max', float, None),
        ),
        'col_widths': (6, 6),  # this affects input sizes in accordions
    },
    'time_gap_test': {
        'fn': od_core.time_gap_test,
        'plain': 'Time gap test',
        'ts_col_type': 'x',
        'args': (
            ('number', 'Number', int, None),
            ('unit', 'Unit', 'date_unit', None),
        ),
        'col_widths': (6, 6),
    },
    'value_gap_test': {
        'fn': od_core.value_gap_test,
        'plain': 'Value gap test',
        'ts_col_type': 'xy',
    },
    'flat_line_test': {
        'fn': od_core.flat_line_test,
        'plain': 'Flat line test',
        'ts_col_type': 'xy',
        'args': (('number_of_repeated_values', 'Repeated Values', int, 2),),
        'col_widths': (6,),
    },
    'z_score_test': {
        'fn': od_core.z_score_test,
        'plain': 'Z-score test',
        'ts_col_type': 'y',
        'args': (('number_of_standard_deviations', 'Standard Deviations', int, 3),),
        'col_widths': (6,),
    },
    'modified_z_score_test': {
        'fn': od_core.modified_z_score_test,
        'plain': 'Modified z-score test',
        'ts_col_type': 'y',
        'args': (('median_absolute_deviation', 'Median Absolute Deviation', float, None),),
        'col_widths': (6,),
    },
    'tukey_iqr_test': {
        'fn': od_core.tukey_iqr_test,
        'plain': 'Tukey IQR test',
        'ts_col_type': 'y',
    },
    'spike_detection_test': {
        'fn': od_core.spike_detection_test,
        'plain': 'Spike detection test',
        'ts_col_type': 'y',
        'args': (('factor', 'Factor', float, 1),),
        'col_widths': (6,),
    },
    'rate_of_change_test': {
        'fn': od_core.rate_of_change_test,
        'plain': 'Rate of change test',
        'ts_col_type': 'y',
        'args': (
            ('threshold_value', 'Threshold Value', float, None),
            ('previous_number_of_points', 'Previous Points', int, None),
        ),
        'col_widths': (6, 6),
    },
}


# Name a column that is the result of running outlier detection
def get_od_name(test_name, test_col):
    return f'{test_col}{_F}{test_name}'


def get_manual_col(y_col):
    return f'{y_col}_{MANUAL}'


# Help identify all columns that are the result of running outlier detection on a column
# or manual flagging.
def get_od_names(df, test_col):
    return [
        col
        for col in df.columns
        if any(
            (
                get_od_name('', test_col) in col,
                get_manual_col(test_col) in col,
            )
        )
    ]


# Hacky way to get the names of all possible outlier detection columns in a dataframe
def get_all_od_names(df: pd.DataFrame):
    return get_od_names(df, '')


# Helps rename plotly elements so that they don't display our ugly internal column
# names on the legend or tooltip. Does nothing if outlier detection hasn't been
# executed yet.
def get_od_col_renames(od_cols) -> dict[str, str]:
    if not od_cols:
        return {}

    renames = {}
    for col in od_cols:
        if MANUAL in col:  # manual flag
            renames[col] = MANUAL
        else:
            value = col[col.find(_F) :].lstrip('_')  # remove internal text
            value = value.replace('_', ' ').capitalize()  # make name look better
            renames[col] = value

    # Internal names need to be in the rename mapping to prevent errors but we
    # don't want them to change.
    renames[PASS] = PASS
    renames[MULTIPLE_FAILURES] = MULTIPLE_FAILURES
    return renames


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
