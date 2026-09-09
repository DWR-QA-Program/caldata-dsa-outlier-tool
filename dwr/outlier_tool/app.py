import asyncio
from io import BytesIO, StringIO

import numpy as np
import pandas as pd
import plotly.express as px
import shinyswatch
from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shiny.types import FileInfo, SilentException
from shinywidgets import render_widget

from . import app_state, app_ui, m, od, od_ui, plot, schema, upload_util, util
from .util import jlog, jlog1, print_func_name


def req(variable):
    util.req(variable, output_fn=jlog1)


def server(input: Inputs, output: Outputs, session: Session):  # noqa: PLR0915
    # Enable theme picker
    shinyswatch.theme_picker_server()

    # State of files uploaded by user and outlier detection results
    user_state = reactive.Value(app_state.State())

    # Container for dynamic upload feedback
    upload_msg = reactive.Value(None)

    # Dynamically-rendered dataframes
    results_df = reactive.Value(pd.DataFrame())
    active_df = reactive.Value(pd.DataFrame())

    # Values used to display dynamic content in the test setup page
    test_setup_info = reactive.Value({})  # left column: test setup options
    user_selected_tests = reactive.Value(od_ui.ODTestSet())  # right column: selected tests

    plot_state = plot.PlotState()

    # Confirm format
    confirmed_format = reactive.Value(None)

    # Review-tab state
    review_date = '__date__'
    review_x_value_col = '__review_x_value__'

    async def run_od(test_list, file_obj: app_state.File):
        try:
            await od.run_od(test_list, file_obj)
            refresh_od_results_manual(file_obj)
        except Exception as e:
            util.show_error(f'Internal error: {e}', duration=5)

    @reactive.effect
    @print_func_name
    def read_file():
        file_info: list[FileInfo] | None = input.file1()
        req(file_info)

        confirmed_format.set(None)

        if msg := upload_util.read_file(
            input,
            file_info,
            user_state,
            invalidate_file_selector,
            _initialize_test_ui,
            _update_x_and_y_cols,
        ):
            upload_msg.set(msg)

    @reactive.effect
    @reactive.event(input.btn_confirm_format)
    def confirm_format():
        req(selected_file := input.sel_files_check())

        shape = input.radio_data_shape()

        if shape not in {'wide', 'long'}:
            util.show_error(
                'Choose how analyte values are listed.'
            )
            return

        is_long = shape == 'long'
        date_col = input.sel_check_date()
        station_col = input.sel_station_col()

        if is_long:
            analyte_name_col = input.sel_long_analyte_col()
            analyte_value_col = input.sel_long_value_col()
            analyte_cols = []

            assigned_cols = [
                station_col,
                date_col,
                analyte_name_col,
                analyte_value_col,
            ]
        else:
            analyte_name_col = None
            analyte_value_col = None
            analyte_cols = list(
                input.sel_wide_analyte_cols() or []
            )

            assigned_cols = [
                station_col,
                date_col,
                *analyte_cols,
            ]

        assigned_cols = [
            col for col in assigned_cols
            if col
        ]

        if len(assigned_cols) != len(set(assigned_cols)):
            util.show_error(
                'Each column can only be assigned one role. '
                'Choose different columns for station, date, and analyte fields.'
            )
            return

        format_info = {
            'is_long': is_long,
            'date_col': date_col,
            'station_col': station_col,
            'analyte_name_col': analyte_name_col,
            'analyte_value_col': analyte_value_col,
            'analyte_cols': analyte_cols,
        }

        confirmed_format.set(format_info)

        file_obj = user_state().get_file(selected_file)

        file_obj.is_long = is_long
        file_obj.last_selected_x_col = date_col
        file_obj.last_selected_station_col = station_col

        if is_long:
            file_obj.analyte_col = analyte_name_col
            file_obj.value_col = analyte_value_col
            file_obj.analyte_cols = []
        else:
            file_obj.analyte_col = None
            file_obj.value_col = None
            file_obj.analyte_cols = analyte_cols

        _initialize_test_ui(file_obj)
        _update_x_and_y_cols(file_obj)

    @render.ui
    def format_preview():
        if confirmed_format() is None:
            return ui.p(
                'Data format has not been confirmed yet. '
                'Confirm the format to preview your data.',
                class_='text-muted',
            )

        return ui.div(
            ui.output_ui('column_color_key'),
            ui.output_data_frame('check_table'),
        )


    # When the user selects a file, they generally expect to see the same selected file on
    # all navigation tabs. We keep all file selectors in sync here to meet this expectation.
    # While it would be more elegant to put a single file selector above or even within the
    # navigation tabs, keeping 4 copies of the selector allows us some UI flexibility.
    def sync_selector(sel_obj: str, other_sel_objs: list[str]):
        @reactive.effect
        def sync_fn():
            selected_value = input[sel_obj]()
            with reactive.isolate():  # prevent infinite reactive loop
                for selector_name in other_sel_objs:
                    ui.update_select(selector_name, selected=selected_value)

        return sync_fn

    # TODO: don't think extended descriptions are a thing? add those in?
    # small edit to avoid the "too many values" error
    @render.ui
    def file_format_info():
        # return schema.get_file_format_info(input.sel_file_format())
        # description, extended_description = schema.get_file_format_info(input.sel_file_format())
        # return (ui.p(description), ui.p(extended_description))
        info = schema.get_file_format_info(input.sel_file_format())
        return ui.p(info)

    @render.ui
    def upload_text():
        msg = upload_msg()
        if msg is None:
            return ui.p('No file uploaded yet.', class_='text-muted')
        return msg

    @render.ui
    def show_rows_to_skip():
        req(input.checkbox_skip_n_rows())
        return ui.input_numeric('input_skip_n_rows', 'Number of rows:', 0, min=0)

    # Show upload options when no file format is selected
    @render.ui
    def upload_options():
        req(ff := input.sel_file_format())
        if ff != m.NO_FF:
            return None
        return app_ui.show_upload_options()

    def _review_analyte(file_obj: app_state.File):
        analytes = file_obj.get_analyte_names()
        selected = file_obj.last_selected_y_col

        if selected not in analytes:
            selected = analytes[0] if analytes else None

        return selected

    def _update_review_against(file_obj: app_state.File, analyte=None):
        analyte = analyte or _review_analyte(file_obj)
        date_col = file_obj.last_selected_x_col

        choices = {}
        if date_col:
            choices[review_date] = date_col

        for other_analyte in file_obj.get_analyte_names():
            if other_analyte != analyte:
                choices[other_analyte] = other_analyte

        selected = review_date if review_date in choices else next(iter(choices), None)

        ui.update_select(
            'sel_review_against',
            choices=choices,
            selected=selected,
        )

    def _update_review_analyte(file_obj: app_state.File):
        analytes = file_obj.get_analyte_names()
        selected = _review_analyte(file_obj)

        ui.update_select(
            'sel_review_analyte',
            choices=analytes,
            selected=selected,
        )

        return selected

    # Keep this legacy callback name because upload_util.read_file() already uses it.
    def _update_x_and_y_cols(file_obj: app_state.File):
        analyte = _update_review_analyte(file_obj)
        _update_review_against(file_obj, analyte)

    @reactive.effect
    def initialize_review_ui():
        req(selected_file := input.sel_files_viz())
        file_obj = user_state().get_file(selected_file)

        _update_x_and_y_cols(file_obj)
        active_df.set(file_obj.df)

    @reactive.effect
    def track_review_analyte():
        req(selected_file := input.sel_files_viz())
        req(analyte := input.sel_review_analyte())

        file_obj = user_state().get_file(selected_file)
        file_obj.last_selected_y_col = analyte
        _update_review_against(file_obj, analyte)


    # color stuff (check tab)
    @render.ui
    def column_color_key():
        format_info = confirmed_format()

        if format_info is None:
            return None

        is_long = format_info['is_long']

        badges = [
            ui.tags.span(
                'Station',
                class_='badge column-station me-2',
            ),
            ui.tags.span(
                'DateTime',
                class_='badge column-datetime me-2',
            ),
        ]

        if is_long:
            badges.extend(
                [
                    ui.tags.span(
                        'Analyte Name',
                        class_='badge column-analyte-name me-2',
                    ),
                    ui.tags.span(
                        'Analyte Value',
                        class_='badge column-analyte-value me-2',
                    ),
                ]
            )
        else:
            badges.append(
                ui.tags.span(
                    'Analyte',
                    class_='badge column-analyte me-2',
                )
            )

        return ui.div(
            ui.tags.span(
                'Column color key:',
                class_='me-2 text-muted small',
            ),
            *badges,
            class_='mb-3',
        )

    # TODO: old stuff
    # Functions related to station ID column

    # Helper: col ID from schema
    def _schema_station_col(file_obj) -> str | None:
        sch = getattr(file_obj, 'schema', None)
        if sch is None:
            return None
        return getattr(sch, 'station_id_column', None)

    # Helper: guess col ID based on station-like keywords
    def _guess_station_col(df: pd.DataFrame) -> str | None:
        if df is None or df.empty:
            return None

        keywords = ('site', 'station', 'location')
        candidates = [
            c for c in df.columns
            if any(k in str(c).strip().lower() for k in keywords)
        ]

        # if none or multiple, no default
        if len(candidates) != 1:
            return None

        return candidates[0]

    # Default station column
    def _default_station_col(file_obj) -> str | None:
        df = getattr(file_obj, 'df', None)
        if df is None or df.empty:
            return None

        # based on schema
        sch_col = _schema_station_col(file_obj)
        if sch_col and sch_col in df.columns:
            return sch_col

        # if not in schema (or none selected), based on col names
        return _guess_station_col(df)

    @reactive.effect
    def update_check_date_selector():
        req(selected_file := input.sel_files_check())
        file_obj = user_state().get_file(selected_file)
        ui.update_select(
            'sel_check_date',
            choices=file_obj.date_cols,
            selected=file_obj.last_selected_x_col,
        )

    @reactive.effect
    def update_station_col_selector():
        req(selected_file := input.sel_files_check())
        file_obj = user_state().get_file(selected_file)
        df = file_obj.df

        if df is None or df.empty:
            ui.update_select('sel_station_col', choices={'': '(none)'}, selected='')
            return

        choices = {'': '(none)', **{c: c for c in df.columns}}

        prev = getattr(file_obj, 'last_selected_station_col', '')
        if prev in df.columns:
            selected = prev
        else:
            selected = _default_station_col(file_obj) or ''
            file_obj.last_selected_station_col = selected

        ui.update_select('sel_station_col', choices=choices, selected=selected)

    # determine current station from either schema or selected column
    # will only return one value; assumption is multiple stations are not (supposed to be) in file
    @reactive.calc
    def current_station_id() -> str | None:
        req(selected_file := input.sel_files_check())
        file_obj = user_state().get_file(selected_file)
        df = file_obj.df
        if df is None or df.empty:
            return None

        station_col = input.sel_station_col()
        if not station_col:
            return None
        if station_col not in df.columns:
            return None

        vals = (
            df[station_col]
            .dropna()
            .astype(str)
            .str.strip()
            .str.upper()
            .unique()
            .tolist()
        )

        return vals[0] if vals else None

    # warning when multiple strings exist in station column
    @render.ui
    def station_col_warning():
        req(selected_file := input.sel_files_check())
        file_obj = user_state().get_file(selected_file)
        df = file_obj.df
        if df is None or df.empty:
            return None

        station_col = input.sel_station_col()
        if not station_col or station_col not in df.columns:
            return None

        vals = df[station_col].dropna().astype(str).str.strip().unique().tolist()
        if len(vals) > 1:
            return util.danger(f'Station column has {len(vals)} unique values. Only the first ({vals[0]}) will be used.')
        return None

    # validate tests aren't missing params
    def validate_test_parameters(test_list):
        incomplete = set()

        method_to_test = {
            method_key: test_key
            for test_key, test_info in od.OD_TESTS.items()
            for method_key in test_info['methods']
        }

        for method_key, analyte, _, kwargs in test_list:
            method_info = od.OD_IMPLEMENTED[method_key]

            for arg_id, *_ in method_info.get('args', ()):
                value = kwargs.get(arg_id)

                if value is None or pd.isna(value):
                    test_key = method_to_test[method_key]
                    test_name = od.OD_TESTS[test_key]['label']
                    incomplete.add((analyte, test_name))

        return incomplete

    @reactive.effect
    @reactive.event(input.btn_od)
    @print_func_name()
    def do_outlier_detection():
        tests = user_selected_tests()

        if len(tests) == 0:
            util.show_warning('You need to select tests first')
            return

        req(selected_file := input.sel_files_test())
        file_obj = user_state().get_file(selected_file)

        test_list = tests.get_test_list(input)

        incomplete = validate_test_parameters(test_list)

        if incomplete:
            util.show_error(
                f'{len(incomplete)} test configuration(s) have missing required settings. '
                'Complete all required fields before running tests.'
            )
            return

        # persist remembered defaults only after validation succeeds
        sid = current_station_id()

        if sid and hasattr(tests, 'persist_station_defaults'):
            tests.persist_station_defaults(sid, input)

        # Keep the Review tab focused on an analyte that was actually tested.
        test_analytes = [analyte for _, analyte, _, _ in test_list]

        if file_obj.last_selected_y_col not in test_analytes:
            for analyte in test_analytes:
                file_obj.last_selected_y_col = analyte
                _update_x_and_y_cols(file_obj)
                break

        # Run the selected outlier tests.
        od_task.invoke(test_list, file_obj)

    # Display data table in "Check" tab
    @render.data_frame
    @reactive.calc
    @print_func_name
    def check_table():
        req(selected_file := input.sel_files_check())

        file_obj = user_state().get_file(selected_file)
        df = file_obj.df

        # Don't show internal columns. Outlier results no longer live on the
        # dataframe, so there's nothing else to filter here.
        df = df[[c for c in df.columns if c not in m.INTERNAL_COLS]]

        format_info = confirmed_format()
        req(format_info)

        station_col = format_info['station_col']
        date_col = format_info['date_col']
        is_long = format_info['is_long']

        analyte_name_col = format_info['analyte_name_col']
        analyte_value_col = format_info['analyte_value_col']
        analyte_cols = set(format_info['analyte_cols'])

        def mapper(col):
            if station_col and col == station_col:
                return 'station'

            if date_col and col == date_col:
                return 'datetime'

            if is_long:
                if col == analyte_name_col:
                    return 'analyte_name'

                if col == analyte_value_col:
                    return 'analyte_value'

            elif col in analyte_cols:
                return 'analyte'

            return None

        asyncio.create_task(
            label_columns(
                list(df.columns.map(mapper))
            )
        )

        return df

    # This function updates our reactive dataframes so that when outlier detection
    # tests are finished running, the results dataframe and plot will update as well.
    def refresh_od_results_manual(file_obj):
        # FIXME: there is a race case here where the user selects a different file
        # while od tests are running, which will result in this function creating
        # results/plots that don't match the currently selected file. This would be
        # easily solved if we could read the currently selected file, but this is not
        # allowed in an ExtendedTask

        file_obj.df = file_obj.df.copy(deep=False)
        active_df.set(file_obj.df)

        results_df.set(file_obj.output_results_as_df())

    # Set up od results table to update automatically when a new file is selected
    @reactive.effect
    def refresh_od_results_auto_test():
        req(selected_file := input.sel_files_test())
        return refresh_od_results_manual(user_state().get_file(selected_file))

    @reactive.effect
    def refresh_od_results_auto_viz():
        req(selected_file := input.sel_files_viz())
        return refresh_od_results_manual(user_state().get_file(selected_file))

    # TODO: update this when flagging happens??
    @render.data_frame
    @reactive.calc
    def od_results_table():
        req(df := results_df())
        return df

    # Kept for compatibility with any older UI that still references this output.
    @render.data_frame
    @reactive.calc
    def od_results_table_viz():
        req(df := results_df())
        req(analyte := input.sel_review_analyte())

        if 'Analyte' in df.columns:
            df = df[df['Analyte'] == analyte]

        keep_cols = [
            col
            for col in ('Analyte', 'Test name', 'Data points that failed')
            if col in df.columns
        ]

        return df[keep_cols] if keep_cols else df

    @render.ui
    def review_test_summary():
        results_df()

        req(selected_file := input.sel_files_viz())
        req(analyte := input.sel_review_analyte())

        file_obj = user_state().get_file(selected_file)

        method_to_test = {
            method_key: test_key
            for test_key, test_info in od.OD_TESTS.items()
            for method_key in test_info['methods']
        }

        failed_by_test = {}

        for (result_analyte, method_key), entry in file_obj.od_results.items():
            if result_analyte != analyte or entry['error'] is not None:
                continue

            test_key = method_to_test.get(method_key)
            if test_key is None:
                continue

            result = entry['result']
            if result is None:
                continue

            result = result.fillna(False).astype(bool)
            failed_by_test.setdefault(test_key, set()).update(
                result[result].index.tolist()
            )

        if not failed_by_test:
            return ui.p(
                'No test results for this analyte.',
                class_='text-muted small',
            )

        rows = []
        for test_key, test_info in od.OD_TESTS.items():
            if test_key not in failed_by_test:
                continue

            rows.append(
                ui.tags.tr(
                    ui.tags.td(
                        test_info['label'],
                        class_='text-center',
                    ),
                    ui.tags.td(
                        len(failed_by_test[test_key]),
                        class_='text-center',
                    ),
                )
            )

        return ui.tags.table(
            ui.tags.thead(
                ui.tags.tr(
                    ui.tags.th(
                        'Test',
                        class_='fw-semibold bg-light',
                        style='text-align: center !important;',
                    ),
                    ui.tags.th(
                        'Failed points',
                        class_='fw-semibold bg-light',
                        style='text-align: center !important;',
                    ),
                )
            ),
            ui.tags.tbody(*rows),
            class_='table table-sm table-bordered mb-0',
        )

    # Build the frame the user downloads: the original data plus one column per
    # test result, flattened out of file_obj.od_results.
    #
    # Wide files get one column per analyte+test ("PH_failed_z_score_test") since
    # each analyte is its own column. Long files get one column per test, filled at
    # the rows belonging to each analyte, because the analyte column already
    # distinguishes them.
    def get_export_df(file_obj):
        df = file_obj.df.copy(deep=False)

        method_to_test = {
            method_key: test_key
            for test_key, test_info in od.OD_TESTS.items()
            for method_key in test_info['methods']
        }

        def result_label(method_key):
            if method_key == 'time_gap_test':
                return 'Missing data before this point'

            if method_key == 'value_gap_test':
                return 'Missing value'

            test_key = method_to_test.get(method_key)

            if test_key is not None:
                return od.OD_TESTS[test_key]['label']

            return od.OD_IMPLEMENTED.get(
                method_key,
                {},
            ).get(
                'plain',
                method_key,
            )

        def outlier_col(analyte):
            if file_obj.is_long:
                return 'outlier'

            return f'{analyte}_outlier'

        def add_result(
            analyte,
            indices,
            label,
        ):
            col = outlier_col(analyte)

            indices = df.index.intersection(
                indices
            )

            if len(indices) == 0:
                return

            current = (
                df.loc[indices, col]
                .fillna('')
                .astype(str)
            )

            df.loc[indices, col] = np.where(
                current.eq(''),
                label,
                current + '; ' + label,
            )

        # Create the final outlier columns.
        if file_obj.is_long:
            df['outlier'] = ''
        else:
            for analyte in file_obj.get_analyte_names():
                df[f'{analyte}_outlier'] = ''

        # Add automated test results.
        for (
            analyte,
            method_key,
        ), entry in file_obj.od_results.items():
            if (
                entry['error'] is not None
                or entry['result'] is None
            ):
                continue

            result = (
                entry['result']
                .fillna(False)
                .astype(bool)
            )

            # Respect flags that the user manually cleared
            # during Review.
            overrides = file_obj.get_flag_overrides(
                analyte
            )

            if overrides:
                result = (
                    result
                    & ~result.index.isin(
                        list(overrides)
                    )
                )

            failed_indices = result[
                result
            ].index

            add_result(
                analyte,
                failed_indices,
                result_label(method_key),
            )

        # Add points manually flagged during Review.
        for analyte, indices in file_obj.manual_flags.items():
            if not indices:
                continue

            add_result(
                analyte,
                indices,
                'Manually flagged',
            )

        return df[
            [
                col
                for col in df.columns
                if col not in m.INTERNAL_COLS
            ]
        ]


    @render.data_frame
    @print_func_name('green')
    def export_table():
        req(selected_file := input.sel_files_export())

        file_obj = user_state().get_file(selected_file)

        df = get_export_df(file_obj)

        selected_export_options = (input.export_settings())

        if (
            'include_header'
            not in selected_export_options
        ):
            asyncio.create_task(
                remove_export_header()
            )

        return df

    def _pair_long_review_data(
        file_obj: app_state.File,
        y_analyte: str,
        x_analyte: str,
    ):
        df = file_obj.df
        date_col = file_obj.last_selected_x_col
        station_col = getattr(file_obj, 'last_selected_station_col', '')
        analyte_col = file_obj.analyte_col
        value_col = file_obj.value_col

        if not all([date_col, analyte_col, value_col]):
            return {
                'df': pd.DataFrame(),
                'x_col': review_x_value_col,
                'warning': None,
                'error': 'The confirmed long-data format is incomplete.',
            }

        keys = [date_col]
        if station_col:
            keys.insert(0, station_col)

        y_rows = df[df[analyte_col] == y_analyte].copy()
        x_rows = df[df[analyte_col] == x_analyte].copy()

        if y_rows.empty:
            return {
                'df': pd.DataFrame(),
                'x_col': review_x_value_col,
                'warning': None,
                'error': f'No observations were found for {y_analyte}.',
            }

        y_complete_keys = y_rows.dropna(subset=keys)
        x_complete_keys = x_rows.dropna(subset=keys)

        y_duplicates = y_complete_keys.duplicated(subset=keys, keep=False)
        x_duplicates = x_complete_keys.duplicated(subset=keys, keep=False)

        if y_duplicates.any() or x_duplicates.any():
            key_text = 'station/date-time' if station_col else 'date-time'
            return {
                'df': pd.DataFrame(),
                'x_col': review_x_value_col,
                'warning': None,
                'error': (
                    f'{x_analyte} cannot be plotted against {y_analyte} because '
                    f'some {key_text} combinations contain multiple values for '
                    'the same analyte.'
                ),
            }

        y_keys = y_rows[[*keys]].copy()
        y_keys['__review_row_index__'] = y_keys.index

        x_values = x_complete_keys[[*keys, value_col]].rename(
            columns={value_col: review_x_value_col}
        )

        paired = y_keys.merge(
            x_values,
            on=keys,
            how='left',
            validate='one_to_one',
            sort=False,
        ).set_index('__review_row_index__')

        valid_y = y_rows[value_col].notna()
        matched = valid_y & paired[review_x_value_col].notna()
        n_total = int(valid_y.sum())
        n_matched = int(matched.sum())

        if n_matched == 0:
            key_text = 'station and date/time' if station_col else 'date/time'
            return {
                'df': pd.DataFrame(),
                'x_col': review_x_value_col,
                'warning': None,
                'error': (
                    f'No {y_analyte} observations could be matched to '
                    f'{x_analyte} by {key_text}.'
                ),
            }

        warning = None
        if n_matched < n_total:
            key_text = 'station and date/time' if station_col else 'date/time'
            warning = (
                f'{n_matched} of {n_total} {y_analyte} observations could be '
                f'matched to {x_analyte} by {key_text}. Unmatched observations '
                'are not shown in this plot.'
            )

        # Keep the original long dataframe shape so plot.py can apply its existing
        # analyte mask. Only the reviewed-analyte rows receive an x value.
        plot_df = df.copy()
        plot_df[review_x_value_col] = np.nan
        matched_indices = paired.index[matched]
        plot_df.loc[matched_indices, review_x_value_col] = paired.loc[
            matched_indices,
            review_x_value_col,
        ]

        return {
            'df': plot_df,
            'x_col': review_x_value_col,
            'warning': warning,
            'error': None,
        }

    @reactive.calc
    def review_plot_info():
        req(selected_file := input.sel_files_viz())
        req(y_analyte := input.sel_review_analyte())
        req(plot_against := input.sel_review_against())

        file_obj = user_state().get_file(selected_file)
        analytes = file_obj.get_analyte_names()

        if y_analyte not in analytes:
            return {
                'df': pd.DataFrame(),
                'x_col': '',
                'warning': None,
                'error': f'{y_analyte} is not a defined analyte.',
            }

        if plot_against == review_date:
            date_col = file_obj.last_selected_x_col
            if not date_col:
                return {
                    'df': pd.DataFrame(),
                    'x_col': '',
                    'warning': None,
                    'error': 'No confirmed date column is available.',
                }

            return {
                'df': file_obj.df,
                'x_col': date_col,
                'warning': None,
                'error': None,
            }

        if plot_against not in analytes:
            return {
                'df': pd.DataFrame(),
                'x_col': '',
                'warning': None,
                'error': f'{plot_against} is not a defined analyte.',
            }

        if not file_obj.is_long:
            return {
                'df': file_obj.df,
                'x_col': plot_against,
                'warning': None,
                'error': None,
            }

        return _pair_long_review_data(
            file_obj,
            y_analyte=y_analyte,
            x_analyte=plot_against,
        )

    @render.ui
    def review_plot_title():
        req(analyte := input.sel_review_analyte())
        req(plot_against := input.sel_review_against())
        req(selected_file := input.sel_files_viz())

        file_obj = user_state().get_file(selected_file)

        if plot_against == review_date:
            plot_against = file_obj.last_selected_x_col

        return ui.div(
            f'{analyte} vs {plot_against}',
            class_='h5 text-center mb-3',
        )

    @render.ui
    def review_match_message():
        info = review_plot_info()

        if info['error']:
            return ui.div(
                info['error'],
                class_='alert alert-danger py-2 mb-3',
            )

        if info['warning']:
            return ui.div(
                info['warning'],
                class_='alert alert-warning py-2 mb-3',
            )

        return None

    @render_widget
    @print_func_name
    def plot_data():
        active_df()

        info = review_plot_info()

        if info['error'] or info['df'].empty:
            return px.scatter()

        req(selected_file := input.sel_files_viz())
        req(analyte := input.sel_review_analyte())
        file_obj = user_state().get_file(selected_file)

        return plot.plot_data(
            info['df'],
            info['x_col'],
            analyte,
            file_obj.schema,
            plot_state,
            file_obj=file_obj,
        )

    # Manual flags and overrides live on the File, not as columns, so writing them
    # is just a state swap followed by a nudge to the reactive dataframe.
    def _commit_flag_state(file_obj, analyte, state):
        file_obj.set_flag_state(analyte, state)

        # See comment in do_outlier_detection function
        dfcp = file_obj.df.copy(deep=False)
        file_obj.df = dfcp
        active_df.set(dfcp)

        invalidate_file_selector('sel_files_export')

    # Manually flag/unflag data points via toggle
    def manual_flag() -> None:
        selected_points = plot_state.get_selected_points()
        if len(selected_points) == 0:
            util.show_warning(
                'No data points are selected. Use the box or lasso selector in the top right.'
            )
            return

        req(selected_file := input.sel_files_viz())
        file_obj = user_state().get_file(selected_file)

        with reactive.isolate():
            analyte = input.sel_review_analyte()

        req(analyte)

        # normalize indices
        selected_points = np.unique(np.asarray(selected_points, dtype=int))

        # Points a test currently flags. Needed so the toggle can tell "clear this
        # test result for this point" apart from "add a manual flag".
        test_flagged = set()
        for entry in file_obj.get_od_results_for(analyte).values():
            if entry['error'] is not None or entry['result'] is None:
                continue
            result = entry['result'].fillna(False).astype(bool)
            test_flagged.update(result[result].index.tolist())

        prev_state = file_obj.get_flag_state(analyte)

        file_obj.toggle_flag(analyte, selected_points, test_flagged)

        new_state = file_obj.get_flag_state(analyte)

        # save previous data to enable undos
        plot_state.add_undo(analyte, prev_state, new_state)
        emphasize_undo_button()

        # wipe out any possible redos
        plot_state.reset_redo()
        unemphasize_redo_button()

        _commit_flag_state(file_obj, analyte, new_state)

    @reactive.effect
    @reactive.event(input.btn_toggle_flag)
    def toggle_flag():
        try:
            manual_flag()
            reset_graph_selection()
        except Exception as e:
            if not isinstance(e, SilentException):
                ui.notification_show(
                    ui.p(f'Please report this to the admin: "toggle_flag": {e!r}'),
                    duration=None,
                    type='error'
                )

    @reactive.effect
    @reactive.event(input.btn_undo_flag)
    def undo_flag():
        try:
            analyte, prev_state = plot_state.undo()
        except IndexError:  # nothing to undo
            return

        emphasize_redo_button()

        if plot_state.undo_stack_is_empty():
            unemphasize_undo_button()

        req(selected_file := input.sel_files_viz())
        _commit_flag_state(user_state().get_file(selected_file), analyte, prev_state)

    @reactive.effect
    @reactive.event(input.btn_redo_flag)
    def redo_flag():
        try:
            analyte, new_state = plot_state.redo()
        except IndexError:  # nothing to redo
            return

        emphasize_undo_button()

        if plot_state.redo_stack_is_empty():
            unemphasize_redo_button()

        req(selected_file := input.sel_files_viz())
        _commit_flag_state(user_state().get_file(selected_file), analyte, new_state)

    def reset_flag_stacks():
        plot_state.reset_stacks()
        unemphasize_undo_button()
        unemphasize_redo_button()

    def reset_graph_selection():
        plot_state.reset_selected_points()

    def reset_manual_flag_objects():
        reset_flag_stacks()
        reset_graph_selection()

    @reactive.effect
    def react_to_new_selected_file():
        req(input.sel_files_viz())
        reset_manual_flag_objects()

    @reactive.effect
    def react_to_new_plot_settings():
        analyte = input.sel_review_analyte()
        plot_against = input.sel_review_against()
        req(analyte and plot_against)
        reset_manual_flag_objects()
        plot_state.reset_zoom()

    def emphasize_undo_button():
        asyncio.create_task(update_button_class('btn_undo_flag', 'btn-light', 'btn-warning'))

    def unemphasize_undo_button():
        asyncio.create_task(update_button_class('btn_undo_flag', 'btn-warning', 'btn-light'))

    def emphasize_redo_button():
        asyncio.create_task(update_button_class('btn_redo_flag', 'btn-light', 'btn-info'))

    def unemphasize_redo_button():
        asyncio.create_task(update_button_class('btn_redo_flag', 'btn-info', 'btn-light'))

    def emphasize_run_tests_button():
        asyncio.create_task(update_button_class('btn_od', 'btn-light', 'btn-primary'))

    def unemphasize_run_tests_button():
        asyncio.create_task(update_button_class('btn_od', 'btn-primary', 'btn-light'))

    def _initialize_test_ui(file_obj):
        is_long = getattr(file_obj, 'is_long', False)
        test_setup_info.set(
            {
                'x_columns': file_obj.date_cols,
                'y_columns': file_obj.num_cols,
                'tests': od.OD_TESTS,
                'is_long': is_long,
                'analytes': file_obj.get_analytes() if is_long else [],
            }
        )

        user_selected_tests.set(od_ui.ODTestSet())
        unemphasize_run_tests_button()

    # When a new file is selected on the test setup tab, this function is responsible
    # for clearing out anything that was there before and repopulating the page with
    # content that will allow the user to set up tests.
    @reactive.effect
    def initialize_test_ui():
        req(selected_file := input.sel_files_test())
        file_obj = user_state().get_file(selected_file)

        _initialize_test_ui(file_obj)

    # Uses data from initialize_test_ui to create ui elements
    @render.ui
    def test_setup_left():
        info = test_setup_info()
        return app_ui._test_setup_left(info)

    @reactive.effect
    @reactive.event(input.btn_test_move)
    def set_up_tests():
        req(selected_file := input.sel_files_test())
        file_obj = user_state().get_file(selected_file)

        selected_date = file_obj.last_selected_x_col
        selected_analytes = list(input.sel_test_analyte() or [])

        selected_tests = [
            *(input.chk_tests_value() or []),
            *(input.chk_tests_sequential() or []),
        ]

        if not selected_tests:
            util.show_error('At least one test must be selected')
            return

        if not selected_analytes:
            util.show_error('At least one analyte must be selected')
            return

        for test_key in selected_tests:
            test_info = od.OD_TESTS[test_key]

            if test_info.get('needs_date') and not selected_date:
                util.show_error(
                    f'The {test_info["label"].lower()} test requires a date column to be selected'
                )
                return

        tests = user_selected_tests()
        added = 0

        for test_key in selected_tests:
            for analyte in selected_analytes:
                value_col = file_obj.value_col if file_obj.is_long else analyte

                added += tests.add(
                    test_key=test_key,
                    test_col=value_col,
                    analyte=analyte,
                    date_col=selected_date or '',
                )

        if added == 0:
            util.show_info('No additional tests were added (duplicates were filtered)')
            return

        if len(tests) > 0:
            emphasize_run_tests_button()

        user_selected_tests.set(tests.copy())

    @reactive.effect
    @reactive.event(input.accordion_trash_icon_clicked)
    def handle_accordion_trash_click():
        req(hash_value := input.accordion_trash_icon_clicked())
        req(tests := user_selected_tests())
        try:
            tests.remove_by_hash(int(hash_value))
        except Exception as e:
            util.show_error(f'Internal error: {e}')
            return

        if len(tests) == 0:
            unemphasize_run_tests_button()
        user_selected_tests.set(tests.copy())  # force ui update

    @render.ui
    def test_setup_right():
        tests = user_selected_tests()

        if len(tests) == 0:
            return ui.p(
                'No tests selected yet.',
                class_='text-muted',
            )

        sid = current_station_id()  # for default persistence

        return ui.div(
            ui.div(
                'Configure selected tests',
                class_='h5 border-bottom pb-2 mb-3',
            ),
            ui.div(
                tests.get_ui(
                    input,
                    station_id=sid,
                ),
                class_='border rounded p-3 bg-light',
            ),
        )

    # Update button class
    async def update_button_class(id, rm, add):
        await session.send_custom_message(
            'update_btn_class',
            {
                'id': id,
                'rm': rm,
                'add': add,
            },
        )

    # This function is called while rendering a dataframe, therefore the client will
    # be forced to wait for the render to complete.
    async def label_columns(column_types):
        await session.send_custom_message(
            'update_column_label',
            {
                'column_types': column_types,
            },
        )

    # This function is called while rendering a dataframe, therefore the client will
    # be forced to wait for the render to complete.
    async def remove_export_header():
        await session.send_custom_message('remove_export_header', {})

    # This is used to force execution of reactive events that depend on the input file
    # selector.
    def invalidate_file_selector(sel_id, selected_file=None):
        if selected_file is None:
            with reactive.isolate():
                req(selected_file := input[sel_id]())
        ui.update_select(sel_id, selected='')
        ui.update_select(sel_id, selected=selected_file)

    def get_export_file_name():
        req(selected_file := input.sel_files_export())
        selected_ext = input.sel_export_format()
        custom_fname = input.text_export_custom_fname()

        if custom_fname:
            if selected_ext not in custom_fname:
                custom_fname += selected_ext
            return custom_fname

        return f'{util.remove_suffix(selected_file)}_screened{selected_ext}'

    @render.ui
    def show_download_button():
        return ui.download_button(
            'download_data',
            'Download file',
            class_='btn-primary',
            style='width: 100%;',
        )

    @render.ui
    def export_filename():
        fname = get_export_file_name()

        return ui.div(
            fname,
            class_='text-muted small text-center mt-2',
        )

    @render.download(filename=get_export_file_name)
    async def download_data(chunk_size=8192):
        req(selected_file := input.sel_files_export())
        file_obj = user_state().get_file(selected_file)

        selected_ext = input.sel_export_format()
        selected_export_options = input.export_settings()

        header = 'include_header' in selected_export_options

        df = get_export_df(file_obj)

        if selected_ext == '.xlsx':
            buffer = BytesIO()
            df.to_excel(buffer, index=False, header=header)
        else:
            buffer = StringIO()
            df.to_csv(buffer, index=False, header=header)

        buffer.seek(0)

        while True:
            # We don't seem to need to encode string values to binary
            chunk = buffer.read(chunk_size)
            if not chunk:
                break
            yield chunk
            await asyncio.sleep(0)  # allow event loop to switch tasks

    #
    # Variables that rely on above functions:
    #
    od_task = reactive.ExtendedTask(run_od)

    # Set up list of anonymous functions with reactive effects. These will be
    # executed by the framework automatically.
    selectors = app_ui.get_file_selector_names()
    fn_list = [  # noqa: F841
        sync_selector(curr_selector, [s for s in selectors if s != curr_selector])
        for curr_selector in selectors
    ]

    @render.ui
    def analyte_selects():
        req(selected_file := input.sel_files_check())
        try:
            file_obj = user_state().get_file(selected_file)
        except KeyError:
            return None

        df = file_obj.df
        if df is None or df.empty:
            return None

        is_long = input.radio_data_shape() == 'long'
        return app_ui._analyte_selects(list(df.columns), file_obj.num_cols, is_long)

    @render.ui
    def data_shape_options():
        req(input.file1())
        return app_ui._data_shape_options()

    @render.ui
    def od_results_summary():
        # Reactive dependency: this changes whenever test results are refreshed.
        results_df()

        req(selected_file := input.sel_files_test())
        file_obj = user_state().get_file(selected_file)

        if not file_obj.od_results:
            return ui.p(
                'No test results yet.',
                class_='text-muted',
            )

        # Map each underlying method back to its user-facing test.
        method_to_test = {
            method_key: test_key
            for test_key, test_info in od.OD_TESTS.items()
            for method_key in test_info['methods']
        }

        # format params helper
        def format_params(method_key, params):
            arg_info = od.OD_IMPLEMENTED[method_key].get('args', ())
            parts = []

            for arg_id, arg_label, *_ in arg_info:
                value = params.get(arg_id)

                if value is not None:
                    parts.append(f'{arg_label} = {value}')

            return '; '.join(parts) if parts else '\u2014'

        rows_by_analyte = {}

        # Missing data is handled separately because its two methods should
        # appear as one result with the union of their failed rows.
        missing_results = {}

        for (analyte, method_key), entry in file_obj.od_results.items():
            if entry['error'] is not None:
                continue

            test_key = method_to_test.get(method_key)
            if test_key is None:
                continue

            test_info = od.OD_TESTS[test_key]

            if test_key == 'missing_data':
                missing_results.setdefault(analyte, []).append(
                    (method_key, entry)
                )
                continue

            method_name = od.OD_IMPLEMENTED[method_key]['plain']

            if test_info.get('method_choices'):
                method_name = test_info['method_choices'].get(
                    method_key,
                    method_name,
                )

            result = entry['result'].fillna(False).astype(bool)
            n_failed = int(result.sum())

            rows_by_analyte.setdefault(analyte, []).append(
                {
                    'Test': test_info['label'],
                    'Method': method_name,
                    'Parameters': format_params(
                        method_key,
                        entry.get('params', {}),
                    ),
                    'n_failed': n_failed,
                }
            )

        # Merge time-gap and value-gap failures into one Missing data row.
        for analyte, entries in missing_results.items():
            failed_indices = set()
            parameter_parts = []

            for method_key, entry in entries:
                result = entry['result'].fillna(False).astype(bool)

                failed_indices.update(
                    result[result].index.tolist()
                )

                params = format_params(
                    method_key,
                    entry.get('params', {}),
                )

                if params != '\u2014':
                    parameter_parts.append(params)

            parameters = (
                '; '.join(dict.fromkeys(parameter_parts))
                if parameter_parts
                else '\u2014'
            )

            rows_by_analyte.setdefault(analyte, []).append(
                {
                    'Test': od.OD_TESTS['missing_data']['label'],
                    'Method': od.OD_TESTS['missing_data']['method_label'],
                    'Parameters': parameters,
                    'n_failed': len(failed_indices),
                }
            )

        if not rows_by_analyte:
            return ui.p(
                'No test results yet.',
                class_='text-muted',
            )

        sections = []

        for analyte, rows in rows_by_analyte.items():
            sections.append(
                ui.div(
                    ui.div(
                        analyte,
                        class_=(
                            'fw-bold px-3 py-2 border-bottom '
                            'bg-secondary-subtle text-center'
                        ),
                    ),
                    ui.tags.table(
                        ui.tags.thead(
                            ui.tags.tr(
                                ui.tags.th(
                                    'Test',
                                    class_='text-center fw-semibold',
                                    style='width: 22%;',
                                ),
                                ui.tags.th(
                                    'Method',
                                    class_='text-center fw-semibold',
                                    style='width: 25%;',
                                ),
                                ui.tags.th(
                                    'Parameters',
                                    class_='text-center fw-semibold',
                                    style='width: 33%;',
                                ),
                                ui.tags.th(
                                    '# of Failed Points',
                                    class_='text-center fw-semibold',
                                    style='width: 20%;',
                                ),
                                class_='table-light',
                            )
                        ),
                        ui.tags.tbody(
                            *[
                                ui.tags.tr(
                                    ui.tags.td(
                                        row['Test'],
                                        class_='text-center',
                                    ),
                                    ui.tags.td(
                                        row['Method'],
                                        class_='text-center',
                                    ),
                                    ui.tags.td(
                                        row['Parameters'],
                                        class_='text-center',
                                    ),
                                    ui.tags.td(
                                        row['n_failed'],
                                        class_='text-center',
                                    ),
                                )
                                for row in rows
                            ]
                        ),
                        class_=(
                            'table table-sm table-bordered '
                            'table-hover mb-0'
                        ),
                    ),
                    class_='border rounded mb-3 overflow-hidden mx-auto',
                    style='max-width: 1150px;',
                )
            )

        return ui.div(*sections)

    # Workflow requirements
    def has_data():
        selected_file = input.sel_files_check()

        if not selected_file:
            return False

        try:
            file_obj = user_state().get_file(selected_file)
        except KeyError:
            return False

        return file_obj.df is not None and not file_obj.df.empty


    def format_is_confirmed():
        return has_data() and confirmed_format() is not None


    def tests_have_run():
        selected_file = input.sel_files_test()

        if not selected_file:
            return False

        try:
            file_obj = user_state().get_file(selected_file)
        except KeyError:
            return False

        return bool(file_obj.od_results)


    def can_define_format():
        return has_data()


    def can_test():
        return has_data() and format_is_confirmed()


    def can_review():
        return can_test() and tests_have_run()


    def can_export():
        return can_test() and tests_have_run()


    @reactive.effect
    def enforce_workflow():
        tab = input.navigation_bar()

        if tab in {
            '2. Define format',
            '3. Test data',
            '4. Review outliers',
            '5. Export',
        } and not has_data():
            util.show_warning(
                'Upload data before continuing.'
            )
            ui.update_navs(
                'navigation_bar',
                selected='1. Upload',
            )
            return

        if tab in {
            '3. Test data',
            '4. Review outliers',
            '5. Export',
        } and not format_is_confirmed():
            util.show_warning(
                'Confirm the data format before continuing.'
            )
            ui.update_navs(
                'navigation_bar',
                selected='2. Define format',
            )
            return

        if tab in {
            '4. Review outliers',
            '5. Export',
        } and not tests_have_run():
            util.show_warning(
                'Run tests before continuing.'
            )
            ui.update_navs(
                'navigation_bar',
                selected='3. Test data',
            )

app = App(app_ui.app_ui, server, debug=False)