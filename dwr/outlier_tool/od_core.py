# Contains core outlier detection functions (tests).
#
# NOTE: The app calls outlier detection functions using the **kwargs construct.
#       Due to this, changing the names of these functions arguments also requires
#       changing values in the OD_IMPLEMENTED dictionary.

import numpy as np
import pandas as pd
from pandas.api.types import is_datetime64_any_dtype
from scipy import stats

DATE_STRS = [
    'days',
    'hours',
    'minutes',
]


def gross_range_test(ts, minimum, maximum) -> pd.Series:
    """
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

    """
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


def time_gap_test(ts: pd.Series, number: int, unit: str, delta=None) -> pd.Series:
    """
    Apply a time gap test. This test identifies data points separated
    by a time period greater than the provided cadence.

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

    """
    if ts.empty:
        raise ValueError('No input data.')
    if not is_datetime64_any_dtype(ts):
        raise ValueError('Input date column does not have a valid datetime data type.')
    if unit not in DATE_STRS and delta is None:
        raise ValueError(f'Input date types must be one of: {DATE_STRS}.')

    cadence = pd.Timedelta(number, unit) if delta is None else delta

    output_ts = ts.diff() > cadence

    # Since the first value has nothing to be compared to, it will always be True.
    # Manually set it to False to prevent confusion.
    output_ts.iloc[0] = False

    return output_ts


def value_gap_test(ts: pd.Series) -> pd.Series:
    """
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

    """
    if ts.empty:
        raise ValueError('No input data.')

    return ts.isna()


def flat_line_test(ts: pd.Series, number_of_repeated_values: int = 2) -> pd.Series:
    """
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

    """
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
    return pd.Series(
        np.abs(z_score) >= number_of_standard_deviations,
        index=ts.index
    )

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
    modified_z_score = (stats.norm.ppf(3 / 4) * (ts - ts.median())) / (
        stats.median_abs_deviation(ts, nan_policy='omit')
    )
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
    upper_limit = quantiles[0.75] + (iqr * 1.5)
    lower_limit = quantiles[0.25] - (iqr * 1.5)
    return (ts > upper_limit) | (ts < lower_limit)


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
    return ts > factor * mean_adjacent


def rate_of_change_test(
    ts: pd.Series, threshold_value: float, previous_number_of_points: int = 5
) -> pd.DataFrame:
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
    return difference.abs() > threshold_value
