import numpy as np
import pandas as pd
from pandas.api.types import is_datetime64_any_dtype

from . import app_state
from .m import PASS, MANUAL, _F

DATE_STRS = [
    'days',
    'hours',
    'minutes',
]


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
        if minimum > maximum:
            raise ValueError('Minimum value cannot exceed maximum value')
        output_ts = (ts > maximum) | (ts <= minimum)
    elif minimum is not None:
        output_ts = ts <= minimum
    else:
        output_ts = ts > maximum

    return output_ts


def time_gap_test_auto(ts: pd.Series) -> pd.Series:
    return time_gap_test(ts, None, None, ts.diff().median())


def time_gap_test(ts: pd.Series, number: int, unit: str, delta=None) -> pd.Series:
    '''
    Apply a time gap test.

    Any gap between data points, either larger or smaller than
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
    output_ts.iloc[0] = False

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
    mask = ts.ne(ts.shift())
    counts = ts.groupby(mask.cumsum()).transform('count')
    output_ts = counts >= number_of_repeated_values
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
