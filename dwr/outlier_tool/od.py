import numpy as np
import pandas as pd

from scipy import stats
from pandas.api.types import is_datetime64_any_dtype

from . import app_state
from .m import PASS, MANUAL, _F

def get_od_name(test_name, x_col, y_col):
    if y_col is None:
        return f'{x_col}{_F}{test_name}'
    else:
        return f'{x_col}_{y_col}{_F}{test_name}'


def get_manual_col(y_col):
    return f'{y_col}_{MANUAL}'


def get_od_names(df, x_col, y_col):
    ret = [col for col in df.columns if any((get_od_name('', x_col, y_col) in col, get_od_name('', x_col, None) in col, get_manual_col(y_col) in col))]
    return ret


def get_all_od_names(df: pd.DataFrame):
    return get_od_names(df, '', '')


def prettify_column_names(figure, od_cols) -> None:
    renames = {
        col: MANUAL if MANUAL in col else col[col.find(_F):].lstrip('_')
        for col in od_cols
    }
    if renames:
        renames[PASS] = PASS
        figure.for_each_trace(lambda x: x.update(
                name=renames[x.name],
                legendgroup=renames[x.name],
                hovertemplate=x.hovertemplate.replace(x.name, renames[x.name])
            ))


def get_default_tests():
    return {
        'x': [time_gap_test_auto],
        'y': [value_gap_test],
    }


def get_tests(file: app_state.File, config):
    if config is not None:
        ret = []
        for test_fn, y_col, kwargs in config:
            for x_col in file.date_cols:
                if True:
                    ret.append((
                        test_fn,
                        x_col,
                        y_col,
                        kwargs,
                    ))
        return ret
    test_types = get_default_tests()

    ret = []
    for date_test in test_types['x']:
        ret.extend(((date_test, x_col, None, {}) for x_col in file.date_cols))
    for value_test in test_types['y']:
        ret.extend(((value_test, x_col, y_col, {}) for x_col in file.date_cols for y_col in file.num_cols))
    return ret


def pH_range_test(ts) -> pd.Series:
    return gross_range_test(ts, 0, 14)


def gross_range_test(ts: pd.Series, minimum: float, maximum: float) -> pd.Series:
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
        A time series where True indicates values outside the bounds and False indicates otherwise.

    Examples
    --------
    >>> output_ts = gross_range_test(ts=df['test_column'], minimum=0, maximum=100)

    '''
    if ts.empty:
        raise ValueError('No input data.')
    if minimum is None:
        raise ValueError('Minimum must be specified.')
    if maximum is None:
        raise ValueError('Maximum must be specified.')
    if minimum > maximum:
        raise ValueError('Maximum value cannot be less than minimum value.')

    output_ts = (ts > maximum) | (ts <= minimum)

    return output_ts


def time_gap_test_auto(ts: pd.Series) -> pd.Series:
    return time_gap_test(ts, None, None, ts.diff().median())


def time_gap_test(ts: pd.Series, number: int, unit: str) -> pd.Series:
    '''
    Apply a time gap test.

    Any gap between data points, either larger or smaller than
    the provided cadence, will be flagged as invalid.  Specifically, the value that
    *follows* a gap will be flagged as failing this test.

    Parameters
    ----------
    ts : pd.Series
        A pandas series with a datetime index.

    number : int
        Number (ex: 1, 2) to define the expected cadence of the data.

    unit : str
        String (ex: days, hours) to define the time unit to measure. pandas.Timedelta must support this.

    Returns
    -------
    pd.Series
        A series where True designates missing values and False designates otherwise.

    Examples
    --------
    >>> output_ts = time_gap_test(ts=df['test_column'], number=1, unit='days'))

    '''
    if ts.empty:
        raise ValueError('No input data.')
    if not is_datetime64_any_dtype(ts):
        raise ValueError('Input date column does not have a valid datetime data type.')
    try:
        item_try = pd.Timedelta(number, unit)
    except ValueError as item_try:
        print(str(item_try))
        print("Use 'hours', 'minutes', or 'days'.")
        return np.nan

    cadence = pd.Timedelta(number, unit)
    output_ts = ts.diff() != cadence

    return output_ts


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
        A series where True designates missing values and False designates otherwise.

    Examples
    --------
    >>> output_ts = value_gap_test(ts=df['test_column'])

    '''
    if ts.empty:
        raise ValueError('No input data.')

    output_ts = ts.isna()

    return output_ts


def flat_line_test(ts: pd.Series, number_of_repeated_values: int = 3) -> pd.Series:
    '''
    Apply a flat line test to a time series.

    Parameters
    ----------
    ts : pd.Series
        A pandas series.

    number_of_repeated_values : int
        The number of consecutive repeated values to indicate an instrumental anomaly (must be > 2).

    Returns
    -------
    pandas.Series
        A series where repeated input values are represented as True values. Repeated missing/null values are not flagged.

    Examples
    --------
    >>> output_ts = flat_line_test(ts=df['test_column'])

    '''
    if ts.empty:
        raise ValueError('No input data.')
    if number_of_repeated_values <= 1:
        raise ValueError('number_of_repeated_values parameter must be > 1.')
    mask = ts.ne(ts.shift())
    counts = ts.groupby(mask.cumsum()).transform('count')
    output_ts = counts >= number_of_repeated_values
    return output_ts


def z_score_test(ts: pd.Series, number_of_standard_deviations: int = 3) -> pd.Series:
    """
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

    """
    if ts.empty:
        raise ValueError('No input data.')
    z_score = stats.zscore(ts, nan_policy='omit')
    output_ts = np.abs(z_score) >= number_of_standard_deviations
    return output_ts


def modified_z_score_test(ts: pd.Series, median_absolute_deviation: float = 4) -> pd.Series:
    """
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

    """
    if ts.empty:
        raise ValueError('No input data.')
    modified_z_score = (stats.norm.ppf(3/4) * (ts - ts.median())) / (stats.median_abs_deviation(ts, nan_policy='omit'))
    output_ts = np.abs(modified_z_score) >= median_absolute_deviation
    return output_ts


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
    output_ts = ((ts > upper_limit) | (ts < lower_limit))
    return output_ts


def spike_detection_test(ts: pd.Series, factor: float = 1.05) -> pd.DataFrame:
    """
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

    """
    if ts.empty:
        raise ValueError('No input data.')
    mean_adjacent = (ts.shift(1) + ts.shift(-1)) / 2
    output_ts = ts > factor*mean_adjacent
    return output_ts


def rate_of_change_test(ts: pd.Series, threshold_value: float, previous_number_of_points: int = 5) -> pd.DataFrame:
    """
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

    """
    if ts.empty:
        raise ValueError('No input data.')
    mean_previous = ts.rolling(window=previous_number_of_points).mean()
    difference = ts - mean_previous
    output_ts = difference.abs() > threshold_value
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
    'z_score_test': {
        'fn': z_score_test,
        'ts_col_type': 'y',
        'args': (
            ('number_of_standard_deviations', 'Standard Deviations', int),
        ),
    },
    'modified_z_score_test': {
        'fn': modified_z_score_test,
        'ts_col_type': 'y',
        'args': (
            ('median_absolute_deviation', 'Median Absolute Deviation', float),
        ),
    },
    'tukey_iqr_test': {
        'fn': tukey_iqr_test,
        'ts_col_type': 'y',
        'args': (),
    },
    'spike_detection_test': {
        'fn': spike_detection_test,
        'ts_col_type': 'y',
        'args': (
            ('factor', 'Factor', float),
        ),
    },
    'rate_of_change_test': {
        'fn': rate_of_change_test,
        'ts_col_type': 'y',
        'args': (
            ('threshold_value', 'Threshold Value', float),
            ('previous_number_of_points', 'Previous Points', int),
        ),
    }
}
