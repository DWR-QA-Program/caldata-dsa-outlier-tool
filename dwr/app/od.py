import numpy as np
import pandas as pd

default_od_col_name = 'is_outlier'

def gross_range_test(time_series, bounds, col_name=default_od_col_name):
    """
    Apply a gross range test to a time series.

    Parameters
    ----------
    time_series : pandas.Series
        The time series to be tested.
    bounds : tuple
        The lower and upper bounds for the test.

    Returns
    -------
    pandas.DataFrame
        The time series with flagged values outside the bounds.
    
    Examples
    --------
    >>> df_out = gross_range_test(df_in, (0, 100))

    """
    df = pd.DataFrame(time_series.copy())
    if df.empty:
        raise ValueError('No input data.')
    if not all(bounds):
        raise ValueError('One of all of the bounds is empty.')
    df[col_name] = np.where(((df > bounds[1]) | ((df <= bounds[0]))), True, False) 
    return df
