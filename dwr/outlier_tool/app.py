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
    upload_msg = reactive.Value()

    # Dynamically-rendered dataframes
    results_df = reactive.Value(pd.DataFrame())
    active_df = reactive.Value(pd.DataFrame())

    # Values used to display dynamic content in the test setup page
    test_setup_info = reactive.Value({})  # left column: test setup options
    user_selected_tests = reactive.Value(od_ui.ODTestSet())  # right column: selected tests

    plot_state = plot.PlotState()

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
        if msg := upload_util.read_file(
            input,
            file_info,
            user_state,
            invalidate_file_selector,
            _initialize_test_ui,
            _update_x_and_y_cols,
        ):
            upload_msg.set(msg)

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
        return upload_msg()

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

    def _update_x_cols(file_obj: app_state.File):
        ui.update_select('sel_x', choices=file_obj.date_cols, selected=file_obj.last_selected_x_col)

    def _update_y_cols(file_obj: app_state.File):
        ui.update_select('sel_y', choices=file_obj.num_cols, selected=file_obj.last_selected_y_col)

    def _update_x_and_y_cols(file_obj: app_state.File):
        _update_x_cols(file_obj)
        _update_y_cols(file_obj)

    # There are 2 selectors for an x and y column on the review page - this function
    # keeps them in sync with the selected file on that page.
    @reactive.effect
    def update_x_and_y_cols():
        req(selected_file := input.sel_files_viz())

        file_obj = user_state().get_file(selected_file)

        _update_x_and_y_cols(file_obj)

        active_df.set(file_obj.df)
        jlog1(f'updated: x={file_obj.last_selected_x_col}, y={file_obj.last_selected_y_col}')

    @reactive.effect
    def track_selected_x_col():
        req(selected_file := input.sel_files_viz())
        req(x_col := input.sel_x())

        user_state().get_file(selected_file).last_selected_x_col = x_col

    @reactive.effect
    def track_selected_y_col():
        req(selected_file := input.sel_files_viz())
        req(y_col := input.sel_y())

        user_state().get_file(selected_file).last_selected_y_col = y_col


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
            setattr(file_obj, 'last_selected_station_col', selected)

        ui.update_select('sel_station_col', choices=choices, selected=selected)

    # track selected col during app use
    @reactive.effect
    def track_selected_station_col():
        req(selected_file := input.sel_files_check())
        col = input.sel_station_col()
        file_obj = user_state().get_file(selected_file)
        setattr(file_obj, 'last_selected_station_col', col)

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


    @reactive.effect
    @reactive.event(input.btn_od)
    @print_func_name()
    def do_outlier_detection():
        tests = user_selected_tests()
        if len(tests) == 0:
            util.show_warning('You need to select tests first')
            return

        # persist remembered defaults
        sid = current_station_id()
        if sid and hasattr(tests, 'persist_station_defaults'):
            tests.persist_station_defaults(sid, input)

        req(selected_file := input.sel_files_test())
        file_obj = user_state().get_file(selected_file)

        test_list = tests.get_test_list(input)

        # The user will, at some point, select x and y columns to plot on the graph. We save
        # these selected columns for the user's convenience. However, before this choice has
        # been made, a default column will be selected in the selector - it will always be the
        # first column, reading a file's columns left to right. In our context, this first
        # column is often a station or sensor number, which is essentially useless to
        # visualize.
        #
        # To make things slightly easier for the user, we instead save the first column which
        # a test was selected on, since they're probably interested in visualizing it. Of
        # course, if the user has already selected a column that was tested, we do not
        # overwrite that saved column.
        test_cols = [test_col for _, test_col, _ in test_list]
        if file_obj.last_selected_x_col not in test_cols:
            for test_col in test_cols:
                if test_col in file_obj.date_cols:
                    file_obj.last_selected_x_col = test_col
                    _update_x_cols(file_obj)
                    break

        if file_obj.last_selected_y_col not in test_cols:
            for test_col in test_cols:
                if test_col in file_obj.num_cols:
                    file_obj.last_selected_y_col = test_col
                    _update_y_cols(file_obj)
                    break

        # Finally, actually run the outlier detection
        od_task.invoke(test_list, file_obj)

    # Display data table in "Check" tab
    @render.data_frame
    @reactive.calc
    @print_func_name
    def check_table():
        req(selected_file := input.sel_files_check())

        file_obj = user_state().get_file(selected_file)
        df = file_obj.df

        # Don't show internal columns or any existing outlier flag columns
        od_cols = od.get_all_od_names(df)
        df = df[[c for c in df.columns if c not in m.INTERNAL_COLS and c not in od_cols]]

        station_col = input.sel_station_col()

        # Enable column header highlighting
        def mapper(col):
            if station_col and col == station_col:
                return 'station'
            if col in file_obj.date_cols:
                return 'datetime'
            if col in file_obj.num_cols:
                return 'numeric'
            return None

        asyncio.create_task(label_columns(list(df.columns.map(mapper))))
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

    # TODO: update this when flagging happens
    @render.data_frame
    @reactive.calc
    def od_results_table_viz():
        req(df := results_df())
        return df

    # Generate the data we will let the user download. To do so, we filter out
    # some columns and apply light transformations to outlier detection results.
    #
    # TODO: update this when flagging happens
    def get_export_df(df, options):
        # Filter out internal/unwanted columns
        ignore_cols = []
        ignore_cols.extend(m.INTERNAL_COLS)

        od_cols = od.get_all_od_names(df)
        if 'include_passing_cols' not in options:
            ignore_cols.extend(col for col in od_cols if df[col].sum() == 0)

        df = df[[c for c in df.columns if c not in ignore_cols]]

        # Loop through any remaining outlier test columns and convert them from true/false
        # to something more easily interpreted
        with pd.option_context('mode.chained_assignment', None):  # ignore warning
            for c in df.columns:
                if c in od_cols:
                    df[c] = df[c].map(
                        {
                            False: np.nan,
                            True: 'failed',
                        }
                    )
        return df

    @render.data_frame
    @print_func_name('green')
    def export_table():
        req(selected_file := input.sel_files_export())
        file_obj = user_state().get_file(selected_file)

        selected_export_options = input.export_settings()

        df = get_export_df(file_obj.df, selected_export_options)

        # The render function doesn't allow us to disable the header so we have to
        # do it manually.
        if 'include_header' not in selected_export_options:
            asyncio.create_task(remove_export_header())

        return df

    @render_widget
    @print_func_name
    def plot_data():
        req(df := active_df())

        x_col = input.sel_x()
        y_col = input.sel_y()

        if df.empty or not all([x_col, y_col]):
            return px.scatter()

        # This happens when the file input value has been changed but the change
        # hasn't propagated to the inputs yet
        if x_col not in df or y_col not in df:
            req(False)  # returning None will wipe out the graph

        req(selected_file := input.sel_files_viz())
        schema = user_state().get_file(selected_file).schema

        return plot.plot_data(df, x_col, y_col, schema, plot_state)

    def set_flags(indices: list, cols: list[str], value: bool | list[bool]) -> None:
        """
        Updates the manual flags of the active dataframe. The whole dataframe won't be
        updated, just the relevant rows and columns specified by "indices" and "cols",
        respectively.

        Parameters
        ----------
        indices : list
            A list of index values belonging to the input dataframe to apply "value" to.
        cols : list
            List of columns to apply "value" to.
        value : bool or list of bools
            The value(s) we want to set our dataframe's selected rows/columns to.
        """

        req(selected_file := input.sel_files_viz())

        # We don't want this function to execute when active_df is changed
        with reactive.isolate():
            df = active_df()

        # This makes use of pandas' overloaded assignment function, allowing a
        # single value or list of values.
        df.loc[indices, cols] = value

        # See comment in do_outlier_detection function
        dfcp = df.copy(deep=False)
        user_state().get_file(selected_file).df = dfcp
        active_df.set(dfcp)

    # Manually flag/unflag data points via toggle
    def manual_flag(value: bool | None) -> None:
        selected_points = plot_state.get_selected_points()
        if len(selected_points) == 0:
            util.show_warning(
                'No data points are selected. Use the box or lasso selector in the top right.'
            )
            return

        # normalize indices
        selected_points = np.unique(np.asarray(selected_points, dtype=int))

        with reactive.isolate():
            df = active_df()
            y_col = input.sel_y()

        manual_y_col = od.get_manual_col(y_col)

        if manual_y_col not in df:
            df[manual_y_col] = False  # initialize column

        # cache original test-flags so a later toggle can restore them
        if not hasattr(plot_state, 'saved_test_flags'):
            plot_state.saved_test_flags = {}  # (y_col, idx) -> list[str]

        # toggle mode
        if value is None:
            od_cols = od.get_od_names(df, y_col)
            if manual_y_col not in od_cols:
                od_cols = [manual_y_col, *od_cols]

            test_cols = [c for c in od_cols if c != manual_y_col]

            prev_values = df.loc[selected_points, od_cols].copy()
            new_df = prev_values.copy()

            # identify whether each point is currently flagged by at least one (not manual) test
            if test_cols:
                test_flagged = (
                    df.loc[selected_points, test_cols]
                    .fillna(False)
                    .astype(bool)
                    .any(axis=1)
                )
            else:
                test_flagged = pd.Series(False, index=selected_points)

            for idx in selected_points:
                key = (y_col, int(idx))

                if bool(test_flagged.loc[idx]):
                    # flagged by at least one test:
                    # clear all flags, but remember which tests were true
                    flagged_tests = (
                        df.loc[idx, test_cols]
                        .fillna(False)
                        .astype(bool)
                    )
                    plot_state.saved_test_flags[key] = flagged_tests[flagged_tests].index.tolist()

                    new_df.loc[idx, od_cols] = False

                else:
                    # currently not test-flagged:
                    # if saved tests exist, restore them; otherwise, toggle manual flag
                    saved = plot_state.saved_test_flags.get(key, [])
                    saved = [c for c in saved if c in df.columns and c in od_cols]

                    if saved:
                        new_df.loc[idx, od_cols] = False
                        new_df.loc[idx, saved] = True
                        new_df.loc[idx, manual_y_col] = False
                    else:
                        cur_manual = bool(df.loc[idx, manual_y_col]) if manual_y_col in df else False
                        new_df.loc[idx, manual_y_col] = not cur_manual

            # build new_values for undo/redo buttons
            if len(od_cols) == 1:
                new_values = [bool(new_df.loc[i, od_cols[0]]) for i in selected_points]
            else:
                new_values = [tuple(new_df.loc[i, od_cols].tolist()) for i in selected_points]

            # save previous data to enable undos
            plot_state.add_undo(selected_points, od_cols, prev_values, new_values)
            emphasize_undo_button()

            # wipe out any possible redos
            plot_state.reset_redo()
            unemphasize_redo_button()

            # apply changes
            for col in od_cols:
                prev_col = prev_values[col].fillna(False).astype(bool).to_numpy()
                next_col = new_df[col].fillna(False).astype(bool).to_numpy()

                idx_on = selected_points[(~prev_col) & (next_col)]
                idx_off = selected_points[(prev_col) & (~next_col)]

                if len(idx_on) > 0:
                    set_flags(idx_on, [col], True)
                if len(idx_off) > 0:
                    set_flags(idx_off, [col], False)

            invalidate_file_selector('sel_files_export')
            return

    @reactive.effect
    @reactive.event(input.btn_toggle_flag)
    def toggle_flag():
        try:
            manual_flag(None)
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
            sel, cols, prev = plot_state.undo()
        except IndexError:  # nothing to undo
            return

        emphasize_redo_button()

        if plot_state.undo_stack_is_empty():
            unemphasize_undo_button()

        set_flags(sel, cols, prev)

    @reactive.effect
    @reactive.event(input.btn_redo_flag)
    def redo_flag():
        try:
            sel, cols, curr = plot_state.redo()
        except IndexError:  # nothing to redo
            return

        emphasize_undo_button()

        if plot_state.redo_stack_is_empty():
            unemphasize_redo_button()

        set_flags(sel, cols, curr)

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
    def react_to_new_plot_cols():
        sel_x = input.sel_x()
        sel_y = input.sel_y()
        req(sel_x or sel_y)
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
        asyncio.create_task(update_button_class('btn_od', 'btn-light', 'btn-info'))

    def unemphasize_run_tests_button():
        asyncio.create_task(update_button_class('btn_od', 'btn-info', 'btn-light'))

    def _initialize_test_ui(file_obj):
        test_setup_info.set(
            {
                'x_columns': file_obj.date_cols,
                'y_columns': file_obj.num_cols,
                'tests': od.OD_IMPLEMENTED,
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
        selected_x_cols = input.x_boxes()
        selected_y_cols = input.y_boxes()
        selected_tests = input.test_boxes()

        # Validate input: one+ test must be selected
        if not selected_tests:
            util.show_warning('At least one test must be selected')
            return

        if not selected_x_cols and not selected_y_cols:
            util.show_warning('At least one column must be selected')
            return

        # Validate input: one+ data/numeric column must be selected if any selected test
        # requires one.
        for test_key in selected_tests:
            if not selected_y_cols and od.OD_IMPLEMENTED[test_key]['ts_col_type'] == 'y':
                plain_name = od.OD_IMPLEMENTED[test_key]['plain'].lower()
                util.show_warning(f'The {plain_name} requires a numeric column to be selected')
                return
            if not selected_x_cols and od.OD_IMPLEMENTED[test_key]['ts_col_type'] == 'x':
                plain_name = od.OD_IMPLEMENTED[test_key]['plain'].lower()
                util.show_warning(f'The {plain_name} requires a date column to be selected')
                return

        tests = user_selected_tests()
        added = 0
        for test_key in selected_tests:
            test_type = od.OD_IMPLEMENTED[test_key]['ts_col_type']

            # We allow the user to select invalid combinations of tests and columns,
            # here is where we filter those out.
            valid_cols = []
            if 'x' in test_type:
                valid_cols.extend(selected_x_cols)
            if 'y' in test_type:
                valid_cols.extend(selected_y_cols)

            for test_col in valid_cols:
                added += tests.add(test_key=test_key, test_col=test_col)

        if added == 0:
            util.show_info('No additional tests were added (duplicates were filtered)')
            return

        if len(tests) > 0:
            emphasize_run_tests_button()

        user_selected_tests.set(tests.copy())  # force ui update

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
        sid = current_station_id() # for default persistence
        # Set up accordion objects
        return ui.panel_well(tests.get_ui(input, station_id=sid))

    @reactive.effect
    @reactive.event(input.btn_test_help)
    def show_test_help_modal():
        ui.modal_show(app_ui.test_help_modal())

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
        fname = get_export_file_name()
        jlog(fname)
        return ui.download_button('download_data', fname, class_='btn-primary')

    @render.download(filename=get_export_file_name)
    async def download_data(chunk_size=8192):
        req(selected_file := input.sel_files_export())
        file_obj = user_state().get_file(selected_file)

        selected_ext = input.sel_export_format()
        selected_export_options = input.export_settings()

        header = 'include_header' in selected_export_options

        df = get_export_df(file_obj.df, selected_export_options)

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


app = App(app_ui.app_ui, server, debug=False)