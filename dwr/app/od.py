# Outlier detection functions
#
# NOTE: The app calls outlier detection functions using the **kwargs construct.
#       Due to this, changing the names of these functions arguments also requires
#       changing values in the OD_IMPLEMENTED dictionary.

import numpy as np
import pandas as pd
from pandas.api.types import is_datetime64_any_dtype

# This is used to denote data that has not "failed" any outlier detection
PASS = 'pass'

MANUAL = 'manual_flag'

DATE_STRS = [ # maybe rename this
    'days',
    'hours',
    'minutes',
]

_F = '_failed_'

# Name a column that is the result of running outlier detection
def get_od_name(x_col, y_col, test_name):
    if y_col is None:
        return f'{x_col}{_F}{test_name}' # whole time series under question
    else:
        return f'{x_col}_{y_col}{_F}{test_name}'


def get_manual_col(y_col):
    return f'{y_col}_{MANUAL}'

# Help identify all columns that are the result of running outlier detection on a column
# or manual flagging.
def get_od_names(df, x_col, y_col):
    ret = [col
        for col in df.columns
        if any((
            get_od_name(x_col, y_col, '') in col,
            get_od_name(x_col, None, '') in col,
            get_manual_col(y_col) in col,
        ))
    ]

    # This feeds into how columns are sorted - we want manual flagging to appear first
    #try:
    #    idx = ret.index(MANUAL)
    #    ret.insert(0, ret.pop(idx))
    #except ValueError: # not found in list
    #    pass

    return ret


# Help rename plotly elements so that they don't display our ugly internal column names.
# Does nothing if outlier detection hasn't been executed yet.
#
# Note that we use internal column names as *values inside a column* to control plot
# markers (color & shape). That is what gets changed here.
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



def gross_range_test(ts, minimum, maximum) -> pd.Series:
    '''
    Apply a gross range test to a time series.

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
        output_ts = (ts > maximum) | (ts <= minimum)
    elif minimum is not None:
        output_ts = ts <= minimum
    else:
        output_ts = ts > maximum

    return output_ts


def time_gap_test(ts: pd.Series, number: int, unit: str) -> pd.Series:
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

    Returns
    -------
    pd.Series
        A boolean series with the same index as time_series.

    Examples
    --------
    >>> df['failed_test'] = time_gap_test(df['test_column'], cadence=pd.Timedelta('1 days'))

    '''
    if ts.empty:
        raise ValueError('No input data.')
    if not is_datetime64_any_dtype(ts):
        raise ValueError('Input date column does not have a valid datetime data type.')
    if unit not in DATE_STRS:
        raise ValueError(f'Input date types must be one of: {DATE_STRS}.')

    cadence = pd.Timedelta(number, unit)

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
        'ts_col_type': 'y',
        'args': (
            ('minimum', 'Min', float),
            ('maximum', 'Max', float),
        ),
    },
    'time_gap_test': {
        'fn': time_gap_test,
        'ts_col_type': 'x',
        'args': (
            ('number', 'Number', int),
            ('unit', 'Unit', 'date_unit'),
        )
    },
    'value_gap_test': {
        'fn': value_gap_test,
        'ts_col_type': 'y',
        'args': (),
    },
    'flat_line_test': {
        'fn': flat_line_test,
        'ts_col_type': 'y',
        'args': (
            ('number_of_repeated_values', 'Repeated Values', int),
        ),
    },
}
