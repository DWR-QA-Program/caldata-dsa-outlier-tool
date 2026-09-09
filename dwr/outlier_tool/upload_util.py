# misc functions related to uploading files to the tool
from collections.abc import Callable

import dateparser
import dateutil
import numpy as np
import pandas as pd
from htmltools import tags
from pandas.api.types import is_numeric_dtype
from shiny import Inputs, reactive, ui
from shiny.types import FileInfo

from . import m, util
from .m import DATETIMECOL
from .schema import Schema, get_schema
from .util import jlog1, print_func_name


def read_file(
    input_obj: Inputs,
    file_info: list[FileInfo],
    user_state: reactive.Value,
    invalidate_fn: Callable,
    test_ui_update_fn: Callable,
    review_update_fn: Callable,
):
    fpath = file_info[0]['datapath']  # file path internal to browser, only used here
    fname = file_info[0]['name']  # file name used as unique key, used in many functions
    fsize = util.get_file_size(fpath)
    fsize_mb = round(fsize / 1_000_000, 1)

    if fsize > m.MAX_FILE_SIZE_BYTES:
        util.show_error(
            f'File size ({fsize_mb} MB) exceeds maximum of {m.MAX_FILE_SIZE_MB} MB',
            duration=None,
        )
        return None
    elif fsize > m.WARN_FILE_SIZE_BYTES:
        util.show_warning(f'File sizes greater than {m.WARN_FILE_SIZE_MB} MB may cause performance issues.')
        progress = ui.Progress(0, 3)  # this needs to be closed before the function completes
    else:
        progress = None

    # Read all upload settings
    with reactive.isolate():
        read_kwargs = {}
        selected_ff = input_obj.sel_file_format()

        if not input_obj.checkbox_data_has_header():
            read_kwargs['header'] = None

        if input_obj.checkbox_skip_n_rows():
            read_kwargs['skiprows'] = input_obj.input_skip_n_rows()

    # Load file
    try:
        util.cond_progress(progress, 0, 'Reading file into python')
        df = actually_read_file(fpath, selected_ff, read_kwargs)
    except Exception as e:
        util.cond_progress_close(progress)
        return format_upload_error_msg(fname, exception=e)

    msg_kw = {}
    # Register file with internal systems
    util.cond_progress(progress, 1, 'Setting up tool internals')
    state = user_state()
    file_obj = state.add_file(fname, df, selected_ff)
    msg_kw['total_cols'] = len(file_obj.df.columns)
    msg_kw['num_date_cols'] = len(file_obj.date_cols)
    msg_kw['num_numeric_cols'] = len(file_obj.num_cols)
    msg_kw['composite_date_col'] = file_obj.composite_date_col

    # Make file available on all relevant tabs
    util.cond_progress(progress, 2, 'Refreshing tool state')
    ui.update_select('sel_files_check', choices=state.get_filenames())
    ui.update_select('sel_files_test', choices=state.get_filenames())
    ui.update_select('sel_files_viz', choices=state.get_filenames())
    ui.update_select('sel_files_export', choices=state.get_filenames())

    # Update selectors to the most recently uploaded file - we only need to update one
    # and the rest will sync with it.
    ui.update_select('sel_files_check', selected=fname)

    # If a user uploads a file more than one time, toggling the header button between
    # uploads, the resulting data may have different column names. If so, we need to
    # make sure to refresh a few tabs so that they don't display the previous column names.
    with reactive.isolate():
        # Refresh table in review tab
        if input_obj.sel_files_check() == fname:
            invalidate_fn('sel_files_check')

        # Refresh test ui in test tab
        if input_obj.sel_files_test() == fname:
            test_ui_update_fn(file_obj)

        # Refresh column names in plot dropdowns
        if input_obj.sel_files_viz() == fname:
            review_update_fn(file_obj)

        # Refresh export table
        if input_obj.sel_files_export() == fname:
            invalidate_fn('sel_files_export')

    util.cond_progress_close(progress)
    jlog1('read_file exit')
    return format_upload_msg(fname, **msg_kw)


# This could support other delimiters
def read_csv(fpath, kwargs):
    df = pd.read_csv(fpath, **kwargs)

    if 'header' in kwargs and kwargs['header'] is None:
        df.rename(
            {col: f'col{i}' for i, col in enumerate(df.columns)},
            axis='columns',
            inplace=True,
        )
    return df


def actually_read_file(fpath, selected_ff, kwargs):
    if schema := get_schema(selected_ff):
        # Override settings from the UI, they only pertain when no file format is selected
        kwargs = schema.pandas_read_csv_arguments

    return read_csv(fpath, kwargs)


def get_empty_cols(df):
    return [col for col in df.columns if df[col].isnull().all()]


def get_date_cols(df, empty, schema: Schema = None):
    ret = []
    for i, col in enumerate(df.columns):
        if col in empty:
            continue

        # Columns should be valid dates if any of the conditions are true:
        if any(
            (
                'date' in col.lower(),
                'time' in col.lower(),
                schema is not None and len(schema.columns) > 0 and schema[i].is_datetime(),
            )
        ):
            ret.append(col)
            continue

        # TODO: call try_parse_date on other columns

    return ret


def get_num_cols(df, empty, schema: Schema = None):
    return [
        col
        for i, col in enumerate(df.columns)
        if all(
            [
                # Check if pandas notices that the column is numeric
                is_numeric_dtype(df[col]),
                # Check if the column isn't completely empty
                col not in empty,
                # Check if the column isn't manually labeled as non-numeric
                schema is None or len(schema.columns) == 0 or schema[i].is_numeric(),
            ]
        )
    ]


def try_parse_date(value, strict=False):
    if pd.isna(value):
        return None

    # Attempt #1
    try:
        return dateutil.parser.parse(value)
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
        return pd.to_datetime(year + day_of_year + hour_and_minutes, format='%Y%j%H%M')
    except ValueError:
        return None


def get_year_cols(df, thresh):
    year_lower_bound = 1900
    year_upper_bound = 2100
    mask = ((df >= year_lower_bound) & (df <= year_upper_bound)).sum() >= thresh
    mask &= df.apply(pd.api.types.is_integer_dtype)
    return df.columns[mask].to_list()


def get_day_of_year_cols(df, thresh):
    last_day_of_year = 366
    mask = ((df >= 0) & (df <= last_day_of_year)).sum() >= thresh
    mask &= df.apply(pd.api.types.is_integer_dtype)
    return df.columns[mask].to_list()


def get_hour_cols(df, thresh):
    last_hour_of_day = 2300
    mask = ((df >= 0) & (df <= last_hour_of_day)).sum() >= thresh
    mask &= df.apply(pd.api.types.is_integer_dtype)
    return df.columns[mask].to_list()


@print_func_name('yellow')
def attempt_composite_date(df, sample_size=10) -> tuple[str | None, str | None, str | None]:
    """
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
    """
    try:
        sample = df.sample(sample_size)
    except ValueError:  # too few rows
        return None, None, None

    # We're only looking for columns that have been read in as integers really
    sample = sample.select_dtypes(exclude=['object'])

    match_thresh = int(sample_size * 0.9)

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
            if (dcol_num := col_name_to_idx[potential_day_col]) != ycol_num + 1:
                continue
            for potential_hour_col in cols_matching_hour:
                if col_name_to_idx[potential_hour_col] != dcol_num + 1:
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


def text_with_help(description, tooltip_text, leading_text=''):
    return ui.TagList(
        ui.span(ui.HTML(f'{leading_text}{description}&nbsp;')),
        ui.tooltip(ui.span('\u2139'), tooltip_text),
    )


def checkbox_with_help(description, tooltip_text, leading_text=''):
    # This adds a space between the checkbox and the text
    return text_with_help(description, tooltip_text, leading_text='&nbsp;')


# Returns ui elements that show the error status of a file upload+parse
def format_upload_error_msg(fname, exception):
    return ui.panel_well(
        util.danger(f'ERROR: could not load {fname}:'),
        ui.p(repr(exception)),
    )


# Returns ui elements that show the status of a file upload+parse
def format_upload_msg(
    fname,
    total_cols: int,
    num_date_cols: int,
    num_numeric_cols: int,
    composite_date_col=None,
):
    elements = []

    if num_date_cols == 0 or num_numeric_cols == 0:
        elements.append(util.warning(ui.HTML(f'Loaded <code>{fname}</code>.')))
    else:
        elements.append(
            util.success(
                ui.HTML(
                    f'Loaded <code>{fname}</code> successfully.',
                )
            )
        )

    other_cols = total_cols - num_date_cols - num_numeric_cols

    # Column counts
    elements.extend(
        [
            ui.p(f'Found {total_cols} column{"s" if total_cols > 1 else ""}:'),
            tags.ul(
                tags.li(f'{num_date_cols} date column{"s" if num_date_cols > 1 else ""}'),
                tags.li(f'{num_numeric_cols} numeric column{"s" if num_numeric_cols > 1 else ""}'),
                tags.li(f'{other_cols} other column{"s" if other_cols > 1 else ""}'),
            ),
        ]
    )

    if composite_date_col:
        elements.append(
            util.info(f'"{composite_date_col}" was programmatically generated and added to the table.')
        )

    # Add warning if there are missing columns
    missing_col_types = None
    if num_date_cols == 0 and num_numeric_cols == 0:
        missing_col_types = 'date and numeric'
    elif num_date_cols == 0:
        missing_col_types = 'date'
    elif num_numeric_cols == 0:
        missing_col_types = 'numeric'

    if missing_col_types:
        elements.append(
            util.warning(f'Tool will not be fully functional due to missing {missing_col_types} columns')
        )

    elements.extend(
        [
            ui.br(),
            ui.p('We will delete this file once you close or refresh the application window.'),
        ]
    )

    return ui.panel_well(elements)


def nullify_hyphens(df) -> tuple[list[str], list[str]]:
    """
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
    """
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
    """
    Renames duplicate DataFrame column names by appending '_1', '_2', etc.

    Modifies the DataFrame in place and returns it.

    Args:
        df (pd.DataFrame): The input DataFrame.

    Returns:
        pd.DataFrame: The DataFrame with deduplicated column names.
    """
    new_cols = []

    for col in df.columns:
        original_col = str(col)  # Our columns shouldn't be integers but this is for safety

        # Handle the rare case where the input column collides with an existing column but
        # already follows the format we're outputting.
        if original_col in new_cols and '_' in original_col:
            original_col = '_'.join(original_col.split('_')[:-1])  # strips "_1" or "_2", for example

        current_col_name = original_col
        count = 0

        # Make sure the generated/original name hasn't been used yet in the final list
        while current_col_name in new_cols:
            count += 1
            current_col_name = f'{original_col}_{count}'

        new_cols.append(current_col_name)

    df.columns = new_cols
    return df

def guess_col(cols, keywords, default=None):
    """
    Returns the first column whose name contains any of the given keywords.

    Keywords are checked in order, so put the most specific ones first. Matching
    is case-insensitive and substring-based, so 'value' matches 'Result Value'.

    Parameters
    ----------
    cols : list
        Column names to search.
    keywords : iterable of str
        Lowercase substrings to look for, in priority order.
    default : any
        Returned when nothing matches. Falls back to the first column if not given.

    Returns
    -------
    The matching column name, or the default.
    """
    for kw in keywords:
        for col in cols:
            if kw in str(col).strip().lower():
                return col

    if default is not None:
        return default
    return cols[0] if cols else None