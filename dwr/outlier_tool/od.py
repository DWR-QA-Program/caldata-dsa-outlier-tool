# Outlier detection functions and functions related to using outlier detection tests.
#
# NOTE: The app calls outlier detection functions using the **kwargs construct.
#       Due to this, changing the names of these functions arguments also requires
#       changing values in the OD_IMPLEMENTED dictionary.
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from pandas.api.types import is_datetime64_any_dtype
from typing import Callable, Optional, Any

from . import app_state
from .m import PASS, MANUAL, _F

DATE_STRS = [ # maybe rename this
    'days',
    'hours',
    'minutes',
]


# Name a column that is the result of running outlier detection
def get_od_name(test_name, test_col):
    return f'{test_col}{_F}{test_name}'


def get_manual_col(y_col):
    return f'{y_col}_{MANUAL}'


# Help identify all columns that are the result of running outlier detection on a column
# or manual flagging.
def get_od_names(df, test_col):
    ret = [col
        for col in df.columns
        if any((
            get_od_name('', test_col) in col,
            get_manual_col(test_col) in col,
        ))
    ]

    # Keep this here for posterity - if we want manual flags to appear on the graph
    # before other flag types, this code can be uncommented.
    #try:
    #    idx = ret.index(MANUAL)
    #    ret.insert(0, ret.pop(idx))
    #except ValueError: # not found in list
    #    pass

    return ret


# Hacky way to get the names of all possible outlier detection columns in a dataframe
def get_all_od_names(df: pd.DataFrame):
    return get_od_names(df, '')


# Help rename plotly elements so that they don't display our ugly internal column names
# on the legend. Does nothing if outlier detection hasn't been executed yet.
#
# Note that we use internal column names as *values inside a column* to control plot
# markers (color & shape). That is what gets changed here, not the names of columns in
# a table.
def prettify_column_names(figure, od_cols) -> None:
    renames = {
        col: MANUAL if MANUAL in col else col[col.find(_F):].lstrip('_')
        for col in od_cols
    }
    if renames:
        renames[PASS] = PASS
        figure.for_each_trace(lambda x: x.update(
                name = renames[x.name],
                legendgroup = renames[x.name],
                hovertemplate = x.hovertemplate.replace(x.name, renames[x.name])
            ))


# Returns list of default tests we can run on any dataset
def get_default_tests(file: app_state.File):
    raise NotImplementedError('needs to account for not using x column')
    test_types = {
        'x': [time_gap_test_auto],
        'y': [value_gap_test],
    }

    ret = []
    for date_test in test_types['x']:
        ret.extend(((date_test, x_col, None, {}) for x_col in file.date_cols))
    for value_test in test_types['y']:
        ret.extend(((value_test, x_col, y_col, {}) for x_col in file.date_cols for y_col in file.num_cols))
    return ret


def get_tests(file: app_state.File):
    df = file.df
    schema = file.schema

    # We don't know anything about this data, just return simple tests
    if schema is None:
        return get_default_tests(file)

    ret = []
    for col in schema:
        # Don't test columns without data
        if col.name in file.empty_cols:
            continue

        # Add tests that are specific to just a date column
        # TODO: support non-auto values from schema
        if col.is_datetime():
            ret.append((time_gap_test_auto, col.name, {}))
            continue

        # Add numeric tests using user-provided schema
        if col.is_numeric():
            for date_col in file.date_cols:
                # Value gap test can be done for all columns
                ret.append((value_gap_test, col.name, {}))

                # Run gross range test when data is present in input columns
                if col.min is not None or col.max is not None:
                    ret.append((gross_range_test, col.name, {'minimum': col.min, 'maximum': col.max}))

    return ret


def gross_range_test(ts, minimum, maximum) -> pd.Series:
    '''
    Apply a gross range test to a time series. Values outside of the provided minimum
    and/or maximum will be flagged as failing. Values matching the min/max will pass.

    Parameters
    ----------
    ts : pandas.Series
        The time series to be tested.
    minimum : float
        The lower bounds for the test (can be None if maximum is not None).
    maximum : float
        The upper bounds for the test (can be None if minimum is not None).

    Returns
    -------
    pandas.Series
        The original time series where True values are outside the bounds and False values are inside.
    
    Examples
    --------
    >>> df['failed_test'] = gross_range_test(df['test_column'], 0, 100)

    '''
    if ts.empty:
        raise ValueError('No input data.')
    if minimum is None and maximum is None:
        raise ValueError('At least 1 min/max parameter must be specified.')

    if minimum is not None and maximum is not None:
        if minimum > maximum:
            raise ValueError('Minimum value cannot exceed maximum value')
        output_ts = (ts > maximum) | (ts < minimum)
    elif minimum is not None:
        output_ts = ts < minimum
    else:
        output_ts = ts > maximum

    return output_ts


def time_gap_test_auto(ts: pd.Series) -> pd.Series:
    return time_gap_test(ts, None, None, ts.diff().median())
    

def time_gap_test(ts: pd.Series, number: int, unit: str, delta=None) -> pd.Series:
    '''
    Apply a time gap test. Any gap between data points, either larger or smaller than
the provided cadence, will be flagged as invalid.  Specifically, the value that
*follows* a gap will be flagged as failing this test.

    Parameters
    ----------
    ts : pd.Series
        A pandas series with a datetime data type.

    number : int
        number of (ex: days, hours, etc) to define the expected cadence of the data.

    unit : str
        Type of time unit to measure (ex: days, hours). pandas.Timedelta must support this.

    delta : pd.Timedelta
        Optional argument that overrides the "number" and "unit" arguments.

    Returns
    -------
    pd.Series
        A boolean series with the same index as time_series.

    Examples
    --------
    >>> df['failed_test'] = time_gap_test(df['test_column'], number=1, unit='days'))

    '''
    if ts.empty:
        raise ValueError('No input data.')
    if not is_datetime64_any_dtype(ts):
        raise ValueError('Input date column does not have a valid datetime data type.')
    if unit not in DATE_STRS and delta is None:
        raise ValueError(f'Input date types must be one of: {DATE_STRS}.')

    cadence = pd.Timedelta(number, unit) if delta is None else delta

    output_ts = ts.diff() != cadence

    # Since the first value has nothing to be compared to, it will always be True.
    # Manually set it to False to prevent confusion.
    output_ts.iloc[0] = False

    return output_ts


# TODO: test this function
def value_gap_test(ts: pd.Series) -> pd.Series:
    '''
    Apply a value gap test to a time series.
    
    Parameters
    ----------
    ts : pd.Series
        A pandas series

    Returns
    -------
    pd.Series
        A boolean series where True values designate missing values

    Examples
    --------
    >>> df['failed_test'] = value_gap_test(df['test_column'])

    '''
    if ts.empty:
        raise ValueError('No input data.')

    output_ts = ts.isna()

    return output_ts


def flat_line_test(ts: pd.Series, number_of_repeated_values: int = 2) -> pd.Series:
    '''
    Apply a flat line test to a time series.

    Parameters
    ----------
    ts : pd.Series
        A pandas series.
    
    number_of_repeated_values : int
        The number of consecutive repeated values to indicate an instrumental anomaly (must be > 1).

    Returns
    -------
    pandas.Series
        A series where repeated input values are represented as True values. Repeated missing/null values are not flagged.
    
    Examples
    --------
    >>> df['failed_test'] = flat_line_test(df['test_column'])

    '''
    if ts.empty:
        raise ValueError('No input data.')
    if number_of_repeated_values is None:
        raise ValueError('number_of_repeated_values parameter must be specified.')
    if number_of_repeated_values <= 1:
        raise ValueError('number_of_repeated_values parameter must be > 1.')

    value_mismatches_prev = ts != ts.shift(1)

    # Create groups of consecutive repeated values. Cumsum will increment the
    # count when values change, resulting in integers we can use as groups
    group_ids = value_mismatches_prev.cumsum()

    # Count the size of each group
    group_sizes = ts.groupby(group_ids).transform('size')

    # Our output will be the groups with a size larger than the tolerable value
    output_ts = group_sizes >= number_of_repeated_values

    return output_ts


OD_IMPLEMENTED = {
    'gross_range_test': {
        'fn': gross_range_test,
        'plain': 'Gross range test',
        'ts_col_type': 'y',
        'args': (
            ('minimum', 'Min', float, None),
            ('maximum', 'Max', float, None),
        ),
        'col_widths': (6,6), # this affects input sizes in accordions
    },
    'time_gap_test': {
        'fn': time_gap_test,
        'plain': 'Time gap test',
        'ts_col_type': 'x',
        'args': (
            ('number', 'Number', int, 1),
            ('unit', 'Unit', 'date_unit', 'hours'),
        ),
        'col_widths': (6,6),
    },
    'value_gap_test': {
        'fn': value_gap_test,
        'plain': 'Value gap test',
        'ts_col_type': 'xy',
    },
    'flat_line_test': {
        'fn': flat_line_test,
        'plain': 'Flat line test',
        'ts_col_type': 'xy',
        'args': (
            ('number_of_repeated_values', 'Repeated Values', int, 2),
        ),
        'col_widths': (6,),
    },
}
