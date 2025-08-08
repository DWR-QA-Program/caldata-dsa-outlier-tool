# Outlier detection functions and functions related to using outlier detection tests.
#
# NOTE: The app calls outlier detection functions using the **kwargs construct.
#       Due to this, changing the names of these functions arguments also requires
#       changing values in the OD_IMPLEMENTED dictionary.

import numpy as np
import pandas as pd
from pandas.api.types import is_datetime64_any_dtype
from scipy import stats

from . import app_state
from .m import _F, MANUAL, MULTIPLE_FAILURES, PASS

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
    return [col
        for col in df.columns
        if any((
            get_od_name('', test_col) in col,
            get_manual_col(test_col) in col,
        ))
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
        if MANUAL in col: # manual flag
            renames[col] = MANUAL
        else:
            value = col[col.find(_F):].lstrip('_') # remove internal text
            value = value.replace('_', ' ').capitalize() # make name look better
            renames[col] = value

    # Internal names need to be in the rename mapping to prevent errors but we
    # don't want them to change.
    renames[PASS] = PASS
    renames[MULTIPLE_FAILURES] = MULTIPLE_FAILURES
    return renames


def apply_renames(figure, renames) -> None:
    if renames:
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
        ret.extend((date_test, x_col, None, {}) for x_col in file.date_cols)
    for value_test in test_types['y']:
        ret.extend((value_test, x_col, y_col, {}) for x_col in file.date_cols for y_col in file.num_cols)
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

    return ts.isna()


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
    return group_sizes >= number_of_repeated_values


def z_score_test(ts: pd.Series, number_of_standard_deviations: int = 3) -> pd.Series:
    '''
    Apply the Scipy Z-Score test to a time series. Flag values based on the number of standard deviations from the mean.

    Parameters
    ----------
    ts : pd.Series
        A pandas series with a datetime index.

    number_of_standard_deviations : int, optional
        The number of standard deviations from the mean to flag. Default is 3.

    Returns
    -------
    pandas.Series
        Outliers flagged as True or False.

    Examples
    --------
    >>> output_ts = z_score_test(ts=df.VALUE)

    '''
    if ts.empty:
        raise ValueError('No input data.')
    z_score = stats.zscore(ts, nan_policy='omit')
    return np.abs(z_score) >= number_of_standard_deviations


def modified_z_score_test(ts: pd.Series, median_absolute_deviation: float = 4) -> pd.Series:
    '''
    Apply the Scipy Z-Score test to a time series. Flag values based on the number of standard deviations from the mean.

    Parameters
    ----------
    ts : pd.Series
        A pandas series with a datetime index.

    median_absolute_deviation : float, optional
        The threshold defining the maximum allowable median absolute deviation. Default is 4.

    Returns
    -------
    pandas.Series
        Outliers flagged as True or False.

    Examples
    --------
    >>> output_ts = z_score_test(ts=df.VALUE)

    '''
    if ts.empty:
        raise ValueError('No input data.')
    modified_z_score = (stats.norm.ppf(3/4) * (ts - ts.median())) / (stats.median_abs_deviation(ts, nan_policy='omit'))
    return np.abs(modified_z_score) >= median_absolute_deviation


def tukey_iqr_test(ts: pd.Series) -> pd.DataFrame:
    """
    Apply Tukey's IQR test to a time series.

    Parameters
    ----------
    ts : pd.Series
        A pandas series with a datetime index.

    Returns
    -------
    pandas.DataFrame
        Outliers flagged as True or False.

    Examples
    --------
    >>> df_out = tukey_iqr_test(ts)

    """
    if ts.empty:
        raise ValueError('No input data.')
    c = stats.norm.ppf(3 / 4) - stats.norm.ppf(1 / 4)
    quantiles = ts.quantile([0.25, 0.75])
    np.squeeze(np.diff(quantiles, axis=0) / c)
    iqr = quantiles[0.75] - quantiles[0.25]
    upper_limit = quantiles[0.75] + (iqr*1.5)
    lower_limit = quantiles[0.25] - (iqr*1.5)
    return ((ts > upper_limit) | (ts < lower_limit))


def spike_detection_test(ts: pd.Series, factor: float = 1.05) -> pd.DataFrame:
    '''
    Identify a spike, defined as a value greater than the mean*factor of the adjacent values, in a time series.

    Parameters
    ----------
    ts : pd.Series
        A pandas series with a datetime index.

    factor : float, optional
        The factor by which the mean of adjacent values is multiplied to determine a spike.

    Returns
    -------
    pandas.DataFrame
        Outliers flagged as True or False.

    Examples
    --------
    >>> df_out = spike_detection_test(ts)

    '''
    if ts.empty:
        raise ValueError('No input data.')
    mean_adjacent = (ts.shift(1) + ts.shift(-1)) / 2
    return ts > factor*mean_adjacent


def rate_of_change_test(ts: pd.Series, threshold_value: float, previous_number_of_points: int = 5) -> pd.DataFrame:
    '''
    The Rate of Change Test compares determines if two values exeed a threshood.

    Specifically, the test compares the mean value of the N-m points, where m
    indicates the number of previous points, to the Nth point and
    determines if the difference between those two numbers exceeds a threshold.

    Parameters
    ----------
    ts : pd.Series
        A pandas series with a datetime index.

    threshold_value : float
        The threshold value for the difference.

    previous_number_of_points : int, optional
        The number of previous points to consider for the mean calculation. Default is 5.

    Returns
    -------
    pandas.DataFrame
        Outliers flagged as True or False.

    Examples
    --------
    >>> df_out = spike_detection_test(ts)

    '''
    if ts.empty:
        raise ValueError('No input data.')
    mean_previous = ts.rolling(window=previous_number_of_points).mean()
    difference = ts - mean_previous
    return difference.abs() > threshold_value


# TODO: make this an object
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
            ('number', 'Number', int, None),
            ('unit', 'Unit', 'date_unit', None),
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
    'z_score_test': {
        'fn': z_score_test,
        'plain': 'Z-score test',
        'ts_col_type': 'y',
        'args': (
            ('number_of_standard_deviations', 'Standard Deviations', int, 3),
        ),
        'col_widths': (6,),
    },
    'modified_z_score_test': {
        'fn': modified_z_score_test,
        'plain': 'Modified z-score test',
        'ts_col_type': 'y',
        'args': (
            ('median_absolute_deviation', 'Median Absolute Deviation', float, None),
        ),
        'col_widths': (6,),
    },
    'tukey_iqr_test': {
        'fn': tukey_iqr_test,
        'plain': 'Tukey IQR test',
        'ts_col_type': 'y',
    },
    'spike_detection_test': {
        'fn': spike_detection_test,
        'plain': 'Spike detection test',
        'ts_col_type': 'y',
        'args': (
            ('factor', 'Factor', float, 1),
        ),
        'col_widths': (6,),
    },
    'rate_of_change_test': {
        'fn': rate_of_change_test,
        'plain': 'Rate of change test',
        'ts_col_type': 'y',
        'args': (
            ('threshold_value', 'Threshold Value', float, None),
            ('previous_number_of_points', 'Previous Points', int, None),
        ),
        'col_widths': (6,6),
    }
}
