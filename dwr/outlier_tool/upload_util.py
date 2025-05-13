# misc functions related to uploading files to the tool
import dateutil
import dateparser

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

from shiny import ui

from . import util
from .util import to_html_list, jlog1, print_func_name
from .m import DATETIMECOL


def read_csv(fpath, options):
    header = 'infer' if 'data_has_header' in options else None

    df = pd.read_csv(fpath, header=header)

    if header is None:
        df.rename(
            {col: f'col{i}' for i, col in enumerate(df.columns)},
            axis='columns',
            inplace=True,
        )

    # Ensure column names are unique - this is needed for the explore tab since the
    # render function only accepts unique column names.
    df = deduplicate_columns(df)

    return df


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


def to_date(year: pd.Series, day_of_year: pd.Series, hour_and_minutes: pd.Series) -> pd.Series:
    if not pd.api.types.is_object_dtype(year):
        year = year.astype(str)

    if not pd.api.types.is_object_dtype(day_of_year):
        # Ex: 0 -> 000, 10 -> 010
        day_of_year = day_of_year.astype(str).str.pad(3, fillchar='0')

    if not pd.api.types.is_object_dtype(hour_and_minutes):
        # Ex: 0 -> 0000, 100 -> 0100
        hour_and_minutes = hour_and_minutes.astype(str).str.pad(4, fillchar='0')

    try:
        # Concatenate and convert
        return pd.to_datetime(year+day_of_year+hour_and_minutes, format='%Y%j%H%M')
    except ValueError:
        return None


def get_year_cols(df, thresh):
    mask = ((df >= 1900) & (df <= 2100)).sum() >= thresh
    mask &= df.apply(pd.api.types.is_integer_dtype)
    return df.columns[mask].to_list()


def get_day_of_year_cols(df, thresh):
    mask = ((df >= 0) & (df <= 366)).sum() >= thresh
    mask &= df.apply(pd.api.types.is_integer_dtype)
    return df.columns[mask].to_list()


def get_hour_cols(df, thresh):
    mask = ((df >= 0) & (df <= 2300)).sum() >= thresh
    mask &= df.apply(pd.api.types.is_integer_dtype)
    return df.columns[mask].to_list()


@print_func_name('yellow')
def attempt_composite_date(df, sample_size=10) -> tuple[str | None, str | None, str | None]:
    '''
    Looks through all columns of the input dataframe and attempts to construct a
    valid datetime column out of 3 columns. These columns must be in succession and
    consist of >= 90% values that respectively match a year, day of the month, and
    hour of the day.
    
    This function operates "inplace" on the input DataFrame.

    Parameters
    ----------
    df : pandas.DataFrame
        The dataframe under question
    sample_size : int
        The number of rows that should be sampled to evaluate date columns on

    Returns
    -------
    tuple
        Contains the names of the columns used to create a date column, or 3 Nones.
    '''
    try:
        sample = df.sample(sample_size)
    except ValueError: # too few rows
        return None, None, None

    # We're only looking for columns that have been read in as integers really
    sample = sample.select_dtypes(exclude=['object'])

    match_thresh = int(sample_size * .9)

    cols_matching_year = get_year_cols(sample, match_thresh)
    cols_matching_day = get_day_of_year_cols(sample, match_thresh)
    cols_matching_hour = get_hour_cols(sample, match_thresh)

    jlog1(cols_matching_year)
    jlog1(cols_matching_day)
    jlog1(cols_matching_hour)

    col_name_to_idx = {col: idx for idx, col in enumerate(df.columns)}

    # Look for columns in succession
    matches = []
    for potential_year_col in cols_matching_year:
        ycol_num = col_name_to_idx[potential_year_col]
        for potential_day_col in cols_matching_day:
            if (dcol_num := col_name_to_idx[potential_day_col]) != ycol_num+1:
                continue
            for potential_hour_col in cols_matching_hour:
                if (hcol_num := col_name_to_idx[potential_hour_col]) != dcol_num+1:
                    continue
                matches.append((potential_year_col, potential_day_col, potential_hour_col))
                jlog1(f'MATCH: {matches[-1]}')

    # If any columns in succession were matched, try to assign them a date type
    for year, day_of_year, hour in matches:
        if (new_col := to_date(df[year], df[day_of_year], df[hour])) is not None:
            # The column is assumed to not exist since it would have been noticed
            df[DATETIMECOL] = new_col
            return year, day_of_year, hour
    return None, None, None


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
        util.danger(msg),
        ui.p(repr(exception)),
    )


# Returns ui elements that show the status of a file upload+parse
def format_upload_msg(msg,
                      hyphen_fixed=[],
                      hyphen_attempted=[],
                      date_cols=[],
                      num_cols=[],
                      composite_date_col=None,
    ):
    elements = [
        ui.p(ui.HTML(msg)), # use HTML tag to support passing raw html text
    ]

    date_len = len(date_cols)
    num_len = len(num_cols)

    # Hyphen conversion info
    if hyphen_fixed:
        elements.extend([
            util.info(f'INFO: successfully converted to numeric type after deleting hyphens:'),
            ui.HTML(to_html_list(hyphen_fixed)),
        ])

    if hyphen_attempted:
        elements.extend([
            util.warning(f'WARNING: deleting hyphens worked but there are still non-numeric values present:'),
            ui.HTML(to_html_list(hyphen_attempted)),
        ])

    # Date column info
    if date_len:
        elements.extend([
            util.success(f'Found {date_len} date column{"s" if date_len > 1 else ""}:'),
            ui.HTML(to_html_list(date_cols)),
        ])
        if composite_date_col:
            elements.extend([
                util.info(f'"{composite_date_col}" was programmatically generated.'),
            ])
    else:
        elements.extend([
            util.warning(f'WARNING: this file will not be plottable due to missing/unparseable date columns.'),
        ])

    # Numeric column info
    if num_len:
        elements.extend([
            util.success(f'Found {num_len} numeric column{"s" if num_len > 1 else ""}:'),
            ui.HTML(to_html_list(num_cols)),
        ])
    else:
        elements.extend([
            util.warning(f'WARNING: this file will not be plottable due to missing numeric columns.'),
        ])
    return ui.panel_well(elements)


def nullify_hyphens(df) -> tuple[list[str], list[str]]:
    '''
    Cleans the input DataFrame by removing values that consist of only hyphen
    characters. Attempts to convert affected columns to a numeric type
    
    This function operates "inplace" on the input DataFrame.

    Parameters
    ----------
    df : pandas.DataFrame
        The dataframe under question

    Returns
    -------
    fixed, attempted
        fixed: list of columns that were cleaned and converted to numeric types
        attempted: list of columns cleaned of hyphens that remained non-numeric
    '''
    fixed = []
    attempted = []

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


def deduplicate_columns(df: pd.DataFrame) -> pd.DataFrame:
    '''
    Renames duplicate DataFrame column names by appending '_1', '_2', etc.

    Modifies the DataFrame in place and returns it.

    Args:
        df (pd.DataFrame): The input DataFrame.

    Returns:
        pd.DataFrame: The DataFrame with deduplicated column names.
    '''
    new_cols = []

    for col in df.columns:
        original_col = str(col) # Our columns shouldn't be integers but this is for safety

        # Handle the rare case where the input column collides with an existing column but
        # already follows the format we're outputting.
        if original_col in new_cols and '_' in original_col:
            original_col = '_'.join(original_col.split('_')[:-1]) # strips "_1" or "_2", for example

        current_col_name = original_col
        count = 0

        # Make sure the generated/original name hasn't been used yet in the final list
        while current_col_name in new_cols:
            count += 1
            current_col_name = f'{original_col}_{count}'

        new_cols.append(current_col_name)

    df.columns = new_cols
    return df
