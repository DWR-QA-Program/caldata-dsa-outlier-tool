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
    """
    if ts.empty:
        raise ValueError('No input data.')

    return ts.isna()


def flat_line_test(ts: pd.Series, number_of_repeated_values: int = 2) -> pd.Series:
    """
    Apply a flat line test to a time series.

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


def spike_detection_test(
    ts: pd.Series,
    percent_difference: float = 20,
    nearby_readings: int = 3,
) -> pd.Series:
    """
    Flag isolated observations that differ substantially from the local median.

    The local median is calculated from nearby observations on both sides of
    the point being tested. The point itself is excluded.
    """
    if ts.empty:
        raise ValueError('No input data.')

    if percent_difference <= 0:
        raise ValueError('Percent difference must be greater than 0.')

    if nearby_readings < 1:
        raise ValueError('Nearby readings must be at least 1.')

    nearby = pd.concat(
        [
            ts.shift(i)
            for i in range(-nearby_readings, nearby_readings + 1)
            if i != 0
        ],
        axis=1,
    )

    local_median = nearby.median(axis=1)
    enough_data = nearby.notna().sum(axis=1) == 2 * nearby_readings

    difference = (ts - local_median).abs()
    percent_diff = difference / local_median.abs() * 100

    percent_diff = percent_diff.mask(
        local_median.eq(0) & difference.eq(0),
        0,
    )
    percent_diff = percent_diff.mask(
        local_median.eq(0) & difference.ne(0),
        np.inf,
    )

    return (percent_diff >= percent_difference) & enough_data


def rate_of_change_test(
    ts: pd.Series,
    percent_change: float = 20,
    nearby_readings: int = 3,
) -> pd.Series:
    """
    Flag abrupt shifts in the local level of a time series.

    The median of a window immediately before each point is compared with
    the median of a window beginning at that point.
    """
    if ts.empty:
        raise ValueError('No input data.')

    if percent_change <= 0:
        raise ValueError('Percent change must be greater than 0.')

    if nearby_readings < 1:
        raise ValueError('Nearby readings must be at least 1.')

    before = pd.concat(
        [ts.shift(i) for i in range(1, nearby_readings + 1)],
        axis=1,
    )

    after = pd.concat(
        [ts.shift(-i) for i in range(nearby_readings)],
        axis=1,
    )

    before_median = before.median(axis=1)
    after_median = after.median(axis=1)

    enough_data = (
        (before.notna().sum(axis=1) == nearby_readings)
        & (after.notna().sum(axis=1) == nearby_readings)
    )

    difference = (after_median - before_median).abs()
    percent_diff = difference / before_median.abs() * 100

    percent_diff = percent_diff.mask(
        before_median.eq(0) & difference.eq(0),
        0,
    )
    percent_diff = percent_diff.mask(
        before_median.eq(0) & difference.ne(0),
        np.inf,
    )

    return (percent_diff >= percent_change) & enough_data
