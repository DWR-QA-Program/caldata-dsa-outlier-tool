# misc functions related to uploading files to the tool
import dateutil
import dateparser

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

from shiny import ui

from util import to_html_list

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


def upload_checkbox(description, tooltip_text):
    return ui.TagList(
        ui.span(
            ui.HTML(f'&nbsp;{description}&nbsp;')
        ),
        ui.tooltip(
            ui.span('\u2139'),
            tooltip_text
        ),
    )


# Returns ui elements that show the error status of a file upload+parse
def format_upload_error_msg(msg, exception):
    return ui.panel_well(
        ui.p(msg),
        ui.br(),
        ui.p(str(exception)),
    )

# Returns ui elements that show the status of a file upload+parse
def format_upload_msg(msg, hyphen_fixed, hyphen_attempted, date_cols, num_cols):
    elements = [
        ui.p(ui.HTML(msg)), # use HTML tag to support passing raw html text
    ]

    date_len = len(date_cols)
    num_len = len(num_cols)

    # Hyphen conversion info
    if hyphen_fixed:
        elements.extend([
            ui.p(f'INFO: successfully converted to numeric type after deleting hyphens:'),
            ui.HTML(to_html_list(hyphen_fixed)),
        ])

    if hyphen_attempted:
        elements.extend([
            ui.p(f'WARNING: deleting hyphens worked but there are still non-numeric values present:'),
            ui.HTML(to_html_list(hyphen_attempted)),
        ])

    # Date column info
    if date_len:
        elements.extend([
            ui.p(f'Found {date_len} date column{"s" if date_len > 1 else ""}:'),
            ui.HTML(to_html_list(date_cols)),
        ])
    else:
        elements.extend([
            ui.p(f'WARNING: this file will not be plottable due to missing date columns.'),
        ])

    # Numeric column info
    if num_len:
        elements.extend([
            ui.p(f'Found {num_len} numeric column{"s" if num_len > 1 else ""}:'),
            ui.HTML(to_html_list(num_cols)),
        ])
    else:
        elements.extend([
            ui.p(f'WARNING: this file will not be plottable due to missing date columns.'),
        ])
    return ui.panel_well(elements)


# Modifies input df inplace
def nullify_hyphens(df):
    fixed = [] # list of columns we successfully converted to numeric types
    attempted = [] # list of columns we removed hyphens from but still couldn't convert

    # Find out ahead of time which columns even contain values with only hyphens
    mask = df.astype(str).apply(lambda col: col.str.match(r'^-+$'))
    affected_columns = mask.any(axis=0)

    df.replace(r'^-+$', np.nan, regex=True, inplace=True)

    for col in df.columns[affected_columns]:
        try:
            df[col] = pd.to_numeric(df[col])
            fixed.append(col)
        except ValueError:
            attempted.append(col)

    return fixed, attempted
