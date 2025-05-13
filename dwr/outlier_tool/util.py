# misc functions
import os
import html
import dateutil
import dateparser
from pathlib import Path
from functools import wraps

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

import shiny
from shiny import ui

from .m import PASS

LOG_MSG = 0

COLORS = {
    None: '\033[0m',
    'red': '\033[31m',
    'green': '\033[32m',
    'yellow': '\033[33m',
    'blue': '\033[34m',
    'purple': '\033[35m',
    'cyan': '\033[36m',
}

# TODO: increase level as call stack grows in depth
def print_func_name(color=None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = None if callable(color) else color
            jlog(f'{COLORS[key]}{func.__name__}\033[0m')
            return func(*args, **kwargs)
        return wrapper

    # Allow calling without parentheses
    if callable(color):
        return decorator(color)
    return decorator


def catch_errors(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f'ERROR: {func.__name__}: {e}')
            return None
    return wrapper


def jlog(msg='', level=0):
    if os.environ.get('LOGLEVEL') is None:
        return
    print(f'JLO: {chr(9)*level}{msg}')

    global LOG_MSG
    LOG_MSG += 1
    if LOG_MSG > 500:
        raise RuntimeError('something has gone wrong')


def jlog1(msg=''):
    return jlog(msg, level=1)
def jlog2(msg=''):
    return jlog(msg, level=2)


# This serves 2 purposes:
# 1. Allow for calling req on a dataframe, which isn't inherently truthy
# 2. Allow for outputting
def req(variable, output_fn=print):
    if isinstance(variable, pd.DataFrame):
        cond = not variable.empty # we don't pass empty dataframes through
    elif isinstance(variable, np.ndarray):
        cond = variable.any()
    else:
        cond = variable

    shiny.req(cond)
    output_fn(f'req passed')


def success(msg):
    return ui.p(msg, class_='text-success')
def warning(msg):
    return ui.p(msg, class_='text-warning')
def danger(msg):
    return ui.p(msg, class_='text-danger')
def info(msg):
    return ui.p(msg, class_='text-info')


def to_html_list(items):
    list_items = ''.join(f'<li>{html.escape(str(item))}</li>' for item in items)
    return f'<ul>{list_items}</ul>'


# When a row has True values for multiple outlier tests, which test should be displayed
# on the "screen" graph? This function aims to solve this issue by finding the first
# column with a True value, left to right. This gives consistency to the graph.
#
# This function is called row-wise on a list of outlier detection columns, producing
# one string value (a column name) for each given row. The output can be used to
# construct a column used for labels in the "screen" graph.
def get_true_first_column_name(row: pd.Series) -> str:
    if row.sum() > 0:
        return row.idxmax()
    else:
        return PASS

def remove_suffix(filename):
    return Path(filename).stem
