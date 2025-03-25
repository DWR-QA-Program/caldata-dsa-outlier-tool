# misc functions
import html
import dateutil
import dateparser
from functools import wraps

import pandas as pd
from pandas.api.types import is_numeric_dtype

import shiny
from shiny import ui

LOG_MSG = 0

# TODO: increase level as call stack grows in depth
def print_func_name(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        jlog(f'{func.__name__}')
        return func(*args, **kwargs)
    return wrapper


def jlog(msg, level=0):
    print(f'JLO: {chr(9)*level}{msg}')

    global LOG_MSG
    LOG_MSG += 1
    if LOG_MSG > 500:
        raise RuntimeError('something has gone wrong')


def jlog1(msg):
    return jlog(msg, level=1)
def jlog2(msg):
    return jlog(msg, level=2)


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


def to_html_list(items):
    list_items = ''.join(f'<li>{html.escape(item)}</li>' for item in items)
    return f'<ul>{list_items}</ul>'


# Returns the name of index in the input series with the first True value, or
# None if none are True.
def get_first_true_column_name(row: pd.Series) -> str:
    if row.sum() > 0:
        return row.idxmax()
    else:
        return 'pass'
