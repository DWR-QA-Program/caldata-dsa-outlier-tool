# misc functions
import dateutil
import dateparser

import pandas as pd
from pandas.api.types import is_numeric_dtype
import shiny

def get_date_cols(df):
    ret = []
    for col in df.columns:
        if 'date' in col.lower():
            ret.append(col)
            continue
        # TODO: call try_parse_date on other columns

    return ret


def get_num_cols(df):
    return [col for col in df.columns if is_numeric_dtype(df[col])]


# TODO: maybe consider allowing user to pass format string
def try_parse_date(value, strict=False):
    # Attempt #1
    try:
        parsed = dateutil.parser.parse(value)
        return parsed
    except dateutil.parser._parser.ParserError:
        pass

    # Attempt #2
    if parsed := dateparser.parse(value):
        return parsed

    # Give up
    if strict:
        return None
    return value


# Help identify columns that are the result of running outlier detection
def get_od_name(column_name):
    return f'{column_name}_is_outlier'


# This serves 2 purposes:
# 1. Allow for calling req on a dataframe, which isn't inherently truthy
# 2. Allow for outputting
def req(variable, output_fn=print):
    if isinstance(variable, pd.DataFrame):
        cond = not variable.empty # we don't support empty dataframes
    else:
        cond = variable

    shiny.req(cond)
    output_fn(f'req passed')
