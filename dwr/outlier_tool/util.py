# misc functions
import html
from functools import wraps
from pathlib import Path

import numpy as np
import pandas as pd
import shiny
from htmltools import TagChild
from shiny import ui

from .m import MULTIPLE_FAILURES, PASS

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
    print(f'JLO: {chr(9)*level}{msg}')


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


def success(msg):
    return ui.p(msg, class_='text-success')
def warning(msg):
    return ui.p(msg, class_='text-warning')
def danger(msg):
    return ui.p(msg, class_='text-danger')
def info(msg):
    return ui.p(msg, class_='text-info')


def show_info(msg: TagChild, duration=3):
    ui.notification_show(msg, duration=duration, type='info')
def show_warning(msg: TagChild, duration=3):
    ui.notification_show(msg, duration=duration, type='warning')
def show_error(msg: TagChild, duration=3):
    ui.notification_show(msg, duration=duration, type='error')


def cond_progress(progress_bar, value, msg, detail=None):
    if progress_bar is None:
        return
    progress_bar.set(value, message=msg, detail=detail)


def cond_progress_close(progress_bar):
    if progress_bar is None:
        return
    progress_bar.close()


def to_html_list(items):
    list_items = ''.join(f'<li>{html.escape(str(item))}</li>' for item in items)
    return f'<ul>{list_items}</ul>'


# This function is used to control data point labeling on the outlier detection
# result graph. Each failing data point should be labeled with its failing test name.
#
# Specificially, this function is called row-wise on all outlier detection columns
# and returns one string value for each given row/data point. This output string
# will be the data point's label.
#
# But, when a row has failed multiple outlier tests, which test should be
# displayed on our graph? This function provides 2 options to solve this issue:
# 1. When "take_first" argument is True and a data point has multiple failures:
#      Return the first failing test name, reading the dataframe left-to right.
#      This is arbitrary but does provide some consistent information to the user.
# 2. When "take_first" argument is False and a data point has multiple failures:
#      When multiple tests have failed, return a generic string to indicate multiple
#      points of failure.
def get_row_label(row: pd.Series, take_first=False) -> str:
    if (n_failures := row.sum()) == 0:
        return PASS

    if take_first or n_failures == 1:
        return row.idxmax()
    else:
        return MULTIPLE_FAILURES


# Returns list of all failing tests for a given data point.
def get_all_failures(row: pd.Series, renames=None) -> str:
    if renames is None:
        renames = {}

    failures = row[row].index
    if failures.empty:
        return 'None'
    return ', '.join(f if f not in renames else renames[f].replace('Failed ', '') for f in failures)


def get_suffix(filename):
    return Path(filename).suffix


def remove_suffix(filename):
    return Path(filename).stem


def get_file_size(filename):
    return Path(filename).stat().st_size
