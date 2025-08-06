import sys
import math
import time
import asyncio
import inspect
from io import StringIO, BytesIO
from pprint import pprint
from functools import partial

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shiny.types import FileInfo, ImgData, SilentException

from shinywidgets import output_widget, render_widget
import shinyswatch

import plotly.express as px
import plotly.graph_objs as go

from . import m, od, od_ui, app_ui, util, app_state, upload_util, schema
from .util import print_func_name, jlog, jlog1, jlog2


def req(variable):
    util.req(variable, output_fn=jlog1)


def server(input: Inputs, output: Outputs, session: Session):

    # Enable theme picker
    shinyswatch.theme_picker_server()

    # State of files uploaded by user and outlier detection results
    user_state = reactive.Value(app_state.State())

    # Container for dynamic upload feedback
    upload_msg = reactive.Value()

    # Dynamically-rendered dataframes
    results_df = reactive.Value(pd.DataFrame())
    active_df = reactive.Value(pd.DataFrame())

    # List of currently selected points on the graph.
    selected_points = []

    # Values used to display dynamic content in the test setup page
    test_setup_info = reactive.Value({}) # left column: test setup options
    user_selected_tests = reactive.Value(od_ui.ODTestSet()) # right column: selected tests

    # Lists of flagging operations, to support the undo/redo buttons.
    # TODO: add undo size limit?
    undo_stack = []
    redo_stack = []


    async def run_od(test_list, file_obj: app_state.File):
        try:
            jlog('run_od')
            n_tests = len(test_list)
            df = file_obj.df

            with ui.Progress(min=0, max=n_tests) as p:

                for i, (test_fn, test_col, kwargs) in enumerate(test_list):
                    test_name = test_fn.__name__

                    msg = f'({i+1}/{n_tests})'
                    p.set(i, message=msg, detail=f'{test_name}')

                    jlog1(f'{test_fn.__name__}: {test_col}')

                    new_col_name = od.get_od_name(test_name, test_col)

                    start_time = time.perf_counter()
                    try:
                        df[new_col_name] = test_fn(df[test_col], **kwargs)
                    except Exception as e:
                        result = repr(e)
                    else:
                        result = df[new_col_name].sum()

                    file_obj.save_od_result(test_name, test_col, result)

                    if (elapsed_time := time.perf_counter()-start_time) < .2:
                        # Slow down text execution so that the progress bar is visible
                        # even when tests execute quickly.
                        sleep_duration = .2
                    else:
                        sleep_duration = 0

                    # Free up the event loop to switch tasks so that the UI can respond
                    # to events while tests are running.
                    await asyncio.sleep(sleep_duration)

            refresh_od_results_manual(file_obj)

        except Exception as e:
            util.show_error(f'Internal error: {e}', duration=5)


    @reactive.effect
    @print_func_name
    def read_file():
        file: list[FileInfo] | None = input.file1()
        req(file)

        fpath = file[0]['datapath'] # file path internal to browser, only used here
        fname = file[0]['name'] # file name used as unique key, used in many functions
        fsize = util.get_file_size(fpath)
        fsize_mb = round(fsize / 1_000_000, 1)

        if fsize > m.MAX_FILE_SIZE_BYTES:
            util.show_error(
                f'File size ({fsize_mb} MB) exceeds maximum of {m.MAX_FILE_SIZE_MB} MB',
                duration=None,
            )
            return
        elif fsize > m.WARN_FILE_SIZE_BYTES:
            util.show_warning(f'File sizes greater than {m.WARN_FILE_SIZE_MB} MB may cause performance issues.')
            progress = ui.Progress(0, 3) # this needs to be closed before the function completes
        else:
            progress = None

        # Read all upload settings
        with reactive.isolate():
            read_kwargs = {}
            selected_ff = input.sel_file_format()

            if not input.checkbox_data_has_header():
                read_kwargs['header'] = None

            if input.checkbox_skip_n_rows():
                read_kwargs['skiprows'] = input.input_skip_n_rows()

        # Load file
        try:
            util.cond_progress(progress, 0, 'Reading file into python')
            df = upload_util.read_file(fpath, selected_ff, read_kwargs)
        except Exception as e:
            upload_msg.set(upload_util.format_upload_error_msg(fname, exception=e))
            util.cond_progress_close(progress)
            return

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
            # Refresh test ui in test tab
            if (selected_file := input.sel_files_test()) == fname:
                _initialize_test_ui(file_obj)

            # Refresh column names in review tab
            if (selected_file := input.sel_files_viz()) == fname:
                _update_x_and_y_cols(file_obj)

        upload_msg.set(upload_util.format_upload_msg(
            fname,
            **msg_kw
        ))

        util.cond_progress_close(progress)
        jlog1(f'read_file exit')


    # When the user selects a file, they generally expect to see the same selected file on
    # all navigation tabs. We keep all file selectors in sync here to meet this expectation.
    # While it would be more elegant to put a single file selector above or even within the
    # navigation tabs, keeping 4 copies of the selector allows us some UI flexibility.
    def sync_selector(sel_obj: str, other_sel_objs: list[str]):
        @reactive.effect
        def sync_fn():
            selected_value = input[sel_obj]()
            with reactive.isolate(): # prevent infinite reactive loop
                for selector_name in other_sel_objs:
                    ui.update_select(selector_name, selected=selected_value)
        return sync_fn


    @render.ui
    def file_format_info():
        return schema.get_file_format_info(input.sel_file_format())
        description, extended_description = schema.get_file_format_info(input.sel_file_format())
        return (ui.p(description), ui.p(extended_description))


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
        ui.update_select('sel_x',
            choices=file_obj.date_cols,
            selected=file_obj.last_selected_x_col
        )
    def _update_y_cols(file_obj: app_state.File):
        ui.update_select('sel_y',
            choices=file_obj.num_cols,
            selected=file_obj.last_selected_y_col
        )

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

        # Enable column header highlighting
        def mapper(col):
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
        with pd.option_context('mode.chained_assignment', None): # ignore warning
            for c in df.columns:
                if c in od_cols:
                    df[c] = df[c].map({
                        False: np.nan,
                        True: 'failed',
                    })
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
            req(False) # returning None will wipe out the graph

        req(selected_file := input.sel_files_viz())
        file_obj = user_state().get_file(selected_file)
        schema = file_obj.schema

        jlog1(f'plot {x_col}/{y_col}')
        jlog1(f'{df[x_col].dtype}')

        px_kwargs = {}
        renames = {}

        if od_cols := od.get_od_names(df, y_col):
            # Set arguments to let plotly know what column to use for markings
            px_kwargs['color'] = px_kwargs['symbol'] = categ_name = m.OUTLIER_TYPE

            # Create the column for controlling markings
            df[categ_name] = df[od_cols].apply(util.get_row_label, axis=1)
            px_kwargs['category_orders'] = {
                categ_name: [m.PASS] + od_cols # keep 'pass' first
            }

            # Create column to show (on hover) what tests failed for a data point
            renames = od.get_od_col_renames(od_cols)
            df[m.FAILURES] = df[od_cols].apply(util.get_all_failures, axis=1, renames=renames)
            px_kwargs['hover_data'] = [m.FAILURES]

        jlog1(f'od_cols: {od_cols}')

        # This will allow us to correlate selected data points with "df"
        df[m.IDX] = df.index

        # Add unit to y-axis label
        if schema is not None and (col_obj := schema.get(y_col, None)) is not None:
            if col_obj.units is not None:
                px_kwargs['labels'] = {
                    y_col: f'{y_col} ({col_obj.units})'
                }

        # We need the graph as a widget so we can register callbacks.
        fig = go.FigureWidget(px.scatter(
            df,
            x=x_col,
            y=y_col,
            custom_data=m.IDX,
            **px_kwargs
        ))

        # Set the "modebar" at the top right of the plot to always display, rather
        # than only display on hover.
        if not hasattr(fig, '_config') or fig._config is None:
            fig._config = {}
        fig._config['displayModeBar'] = True

        # Rename outlier detection columns so they display nicely in the legend.
        od.apply_renames(fig, renames)

        # Set up callbacks for when data is selected
        for i, trace in enumerate(fig.data):
            trace.on_selection(partial(callback_data_selected, trace_num=i))

        # Set up callback for when data is deselected - this only needs to happen
        # for one of the traces.
        fig.data[0].on_deselect(callback_clear_selection)

        return fig


    # Note about callbacks: Plotly catches and completely ignores exceptions within
    # callback functions. We catch and print them to make debugging possible.

    # This is executed on each trace in the graph (i.e. each set of labeled points,
    # like "pass", "test1", "test2", etc). Each trace has a 0-indexed list of indices -
    # these are the points on the graph that have been selected. We use the customdata
    # parameter set up for us to map these values to the values in the original DataFrame.
    @util.catch_errors
    def callback_data_selected(trace, points, selector, trace_num: int) -> None:
        nonlocal selected_points

        jlog1(f'trace #{trace_num}: {trace.legendgroup}')

        # The shape of customdata is a list of lists, each with 1 element. Get
        # that 1 element for selected indices.
        df_indices = trace.customdata[points.point_inds, 0]

        if trace_num == 0:
            selected_points = df_indices
        else:
            selected_points = np.append(selected_points, df_indices)


    # Prevent manual flagging buttons from doing anything when data is deselected
    @util.catch_errors
    def callback_clear_selection(trace, points) -> None:
        nonlocal selected_points
        selected_points = []


    def set_flags(indices: list, cols: list[str], value: bool|list[bool]) -> None:
        '''
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
        '''

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


    def manual_flag(value: bool) -> None:
        if len(selected_points) == 0:
            util.show_warning(f'No data points are selected. Use the box or lasso selector in the top right.')
            return

        with reactive.isolate():
            df = active_df()
            x_col = input.sel_x()
            y_col = input.sel_y()

        manual_y_col = od.get_manual_col(y_col)

        if manual_y_col not in df:
            df[manual_y_col] = False # Populate entire column with False initially

        if value:
            # We want to flag a column
            target_cols = [manual_y_col]
            new_values = [value for _ in selected_points]
        else:
            # We want to unflag all relevant columns (a data point may have failed more than
            # one outlier test).
            target_cols = od.get_od_names(df, y_col)
            new_values = [tuple(value for _ in target_cols) for _ in selected_points]

        prev_values = df.loc[selected_points, target_cols].copy()

        # Save previous data to enable undos
        undo_stack.append((selected_points, target_cols, prev_values, new_values))
        emphasize_undo_button()

        # Wipe out any possible redos
        nonlocal redo_stack
        redo_stack = []
        unemphasize_redo_button()

        set_flags(selected_points, target_cols, value)

        invalidate_file_selector('sel_files_export')


    @reactive.effect
    @reactive.event(input.btn_flag)
    def flag():
        try:
            manual_flag(True)
            reset_graph_selection() # could be removed if the graph isn't always reloaded
        except Exception as e:
            if not isinstance(e, SilentException):
                ui.notification_show(ui.p(f'Please report this to James: "flag": {repr(e)}'), duration=None, type='error')


    @reactive.effect
    @reactive.event(input.btn_unflag)
    def unflag():
        try:
            manual_flag(False)
            reset_graph_selection() # could be removed if the graph isn't always reloaded
        except Exception as e:
            if not isinstance(e, SilentException):
                ui.notification_show(ui.p(f'Please report this to James: "unflag": {repr(e)}'), duration=None, type='error')


    @reactive.effect
    @reactive.event(input.btn_undo_flag)
    def undo_flag():
        try:
            sel, cols, prev, curr = undo_stack.pop()
        except IndexError: # nothing to undo
            return

        redo_stack.append((sel, cols, prev, curr))
        emphasize_redo_button()

        if not undo_stack:
            unemphasize_undo_button()

        set_flags(sel, cols, prev)


    @reactive.effect
    @reactive.event(input.btn_redo_flag)
    def redo_flag():
        try:
            sel, cols, prev, curr = redo_stack.pop()
        except IndexError: # nothing to redo
            return

        undo_stack.append((sel, cols, prev, curr))
        emphasize_undo_button()

        if not redo_stack:
            unemphasize_redo_button()

        set_flags(sel, cols, curr)


    def reset_flag_stacks():
        nonlocal redo_stack, undo_stack
        undo_stack = []
        redo_stack = []
        unemphasize_undo_button()
        unemphasize_redo_button()


    def reset_graph_selection():
        nonlocal selected_points
        selected_points = []


    def reset_manual_flag_objects():
        reset_flag_stacks()
        reset_graph_selection()


    @reactive.effect
    def react_to_new_selected_file():
        req(selected_file := input.sel_files_viz())
        reset_manual_flag_objects()


    @reactive.effect
    def react_to_new_screen_cols():
        sel_x = input.sel_x()
        sel_y = input.sel_y()
        req(sel_x or sel_y)
        reset_manual_flag_objects()


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
        test_setup_info.set({
            'x_columns': file_obj.date_cols,
            'y_columns': file_obj.num_cols,
            'tests': od.OD_IMPLEMENTED,
        })

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
                added += tests.add(
                    test_key=test_key,
                    test_col=test_col
                )

        if added == 0:
            util.show_info('No additional tests were added (duplicates were filtered)')
            return

        if len(tests) > 0:
            emphasize_run_tests_button()

        user_selected_tests.set(tests.copy()) # force ui update


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
        user_selected_tests.set(tests.copy()) # force ui update


    @render.ui
    def test_setup_right():
        tests = user_selected_tests()

        # Set up accordion objects
        right_ui = ui.panel_well(tests.get_ui(input))

        return right_ui


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
            }
        )


    # This function is called while rendering a dataframe, therefore the client will
    # be forced to wait for the render to complete.
    async def label_columns(column_types):
        await session.send_custom_message(
            'update_column_label',
            {
                'column_types': column_types,
            }
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


    @render.download(
        filename=get_export_file_name
    )
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
            await asyncio.sleep(0) # allow event loop to switch tasks


    #
    # Variables that rely on above functions:
    #
    od_task = reactive.ExtendedTask(run_od)

    selectors = app_ui.get_file_selector_names()
    fn_list = [ # list of anonymous functions with reactive effects
        sync_selector(curr_selector, [s for s in selectors if s != curr_selector])
        for curr_selector in selectors
    ]



app = App(app_ui.app_ui, server, debug=False)
