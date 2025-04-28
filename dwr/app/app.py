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

import m
import od
import app_ui
import util
import app_state
import upload_util
from util import print_func_name, jlog, jlog1, jlog2


def req(variable):
    util.req(variable, output_fn=jlog1)


def server(input: Inputs, output: Outputs, session: Session):

    # Enable theme picker
    shinyswatch.theme_picker_server()

    # Values just used in the 'upload' page
    upload_msg = reactive.Value()
    upload_od_feedback = reactive.Value()

    # Values just used in the 'visualize' page
    user_state = reactive.Value(app_state.State())
    active_df = reactive.Value(pd.DataFrame())

    # List of currently selected points on a graph.
    selected_points = []

    # Lists of flagging operations, to support the undo/redo buttons.
    # TODO: add undo size limit?
    undo_stack = []
    redo_stack = []


    async def auto_od(file_obj: app_state.File, config=None):
        try:
            jlog('auto_od')
            test_list = od.get_tests(file_obj, config)
            n_tests = len(test_list)
            df = file_obj.df

            with ui.Progress(min=0, max=n_tests) as p:

                for i, (test_fn, x_col, y_col, kwargs) in enumerate(test_list):
                    test_name = test_fn.__name__
                    test_column = x_col if y_col is None else y_col

                    msg = f'({i+1}/{n_tests})'
                    dtl = f'{test_name}'#: {test_column}'
                    p.set(i, message=msg, detail=dtl)

                    jlog1(f'{test_fn.__name__}: {x_col} {y_col}')

                    new_col_name = od.get_od_name(test_name, x_col, y_col)

                    try:
                        df[new_col_name] = test_fn(df[test_column], **kwargs)
                    except Exception as e:
                        result = repr(e)
                    else:
                        result = df[new_col_name].sum()

                    file_obj.save_od_result(test_name, x_col, y_col, result)

                    await asyncio.sleep(.1)

            upload_od_feedback.set(file_obj.format_results())
            jlog1('done here')
        except Exception as e:
            upload_od_feedback.set(util.danger(repr(e)))


    od_task = reactive.ExtendedTask(auto_od)


    @reactive.effect
    @print_func_name
    def read_file():
        file: list[FileInfo] | None = input.file1()
        req(file)

        fpath = file[0]['datapath'] # file path internal to browser, only used here
        fname = file[0]['name'] # file name used as unique key, used all over

        with reactive.isolate():
            selected_upload_options = input.upload_settings()

        # Load file
        try:
            df = upload_util.read_csv(fpath, selected_upload_options)
        except Exception as e:
            upload_msg.set(upload_util.format_upload_error_msg(f'ERROR: could not load {fname}:', exception=e))
            return

        msg_kw = {}

        # Preprocess data if needed
        if 'upload_nullify_hyphens' in selected_upload_options:
            # operates inplace on df
            msg_kw['hyphen_fixed'], msg_kw['hyphen_attempted'] = upload_util.nullify_hyphens(df)

        # Register file with internal systems
        state = user_state()
        file_obj = state.add_file(fname, df)
        msg_kw['date_cols'] = file_obj.date_cols
        msg_kw['num_cols'] = file_obj.num_cols
        msg_kw['composite_date_col'] = file_obj.composite_date_col

        ui.update_select('sel_files_viz', choices=state.get_filenames())
        ui.update_select('sel_files_table', choices=state.get_filenames())
        ui.update_select('sel_files_columns', choices=state.get_filenames())
        ui.update_select('sel_files_export', choices=state.get_filenames())

        upload_msg.set(upload_util.format_upload_msg(
            f'Loaded <code>{fname}</code> successfully.',
            **msg_kw
        ))

        upload_od_feedback.set(ui.p('Processing...'))

        # Run outlier detection
        od_task.invoke(file_obj)

        jlog1(f'read_file exit')


    @render.ui
    def upload_text():
        return upload_msg()


    @render.ui
    @print_func_name('cyan')
    def show_upload_od_feedback():
        req(od_feedback := upload_od_feedback())
        return ui.panel_well(od_feedback)


    @reactive.effect
    @print_func_name
    def update_x_and_y_cols():
        if not (selected_file := input.sel_files_viz()):
            jlog1(f'no selected_file')
            return

        file_info = user_state().get_file(selected_file)

        ui.update_select('sel_x',
            choices=file_info.date_cols,
            selected=file_info.last_selected_x_col
        )
        ui.update_select('sel_y',
            choices=file_info.num_cols,
            selected=file_info.last_selected_y_col
        )

        active_df.set(file_info.df)
        jlog1(f'updated: x={file_info.last_selected_x_col}, y={file_info.last_selected_y_col}')


    @reactive.effect
    @print_func_name
    def track_selected_x_col():
        if not (selected_file := input.sel_files_viz()):
            jlog1(f'no selected_file')
            return
        if not (x_col := input.sel_x()):
            jlog1(f'no xcol')
            return

        jlog1(x_col)
        user_state().get_file(selected_file).last_selected_x_col = x_col


    @reactive.effect
    @print_func_name
    def track_selected_y_col():
        if not (selected_file := input.sel_files_viz()):
            jlog1(f'no selected_file')
            return
        if not (y_col := input.sel_y()):
            jlog1(f'no ycol')
            return

        jlog1(y_col)
        user_state().get_file(selected_file).last_selected_y_col = y_col


    @reactive.effect
    #@print_func_name
    def updateminmax():
        if not (y_col := input.sel_y()): #TODO: use req?
            #jlog1(f'no ycol')
            return

        df = active_df()
        req(df)

        # This happens when the file has been changed but the change hasn't
        # propagated to the inputs yet
        if y_col not in df:
            jlog1(f'invalid col')
            return None

        min_y = int(df[y_col].min())
        max_y = int(df[y_col].max())
        ui.update_numeric('num_od_min', value=min_y)
        ui.update_numeric('num_od_max', value=max_y)


    @reactive.effect
    @reactive.event(input.btn_od)
    @print_func_name('cyan')
    def do_outlier_detection():
        req(df := active_df()) # not sure why this doesn't appear to need to be isolated

        req(sel_od_fns := input.sel_od_functions())

        req(x_col := input.sel_x())
        req(y_col := input.sel_y())

        req(selected_file := input.sel_files_viz())

        # Loop through all selected outlier detection methods and apply them serially
        for sel_od in sel_od_fns:
            try:
                od_info = od.OD_IMPLEMENTED[sel_od]
            except KeyError: # this can only happen if a user messes with the selections
                jlog1('very unexpected KeyError: {sel_od}')
                continue

            kwargs = {}

            if od_info['ts_col_type'] == 'y': # most cases
                data = df[y_col]
                new_col_name = od.get_od_name(sel_od, x_col, y_col)
            else:
                data = df[x_col]
                new_col_name = od.get_od_name(sel_od, x_col, None)
            kwargs['ts'] = data

            jlog1(f'new_col_name: {new_col_name}')

            for arg_id, arg_label, arg_type in od_info['args']:
                input_id = f'{sel_od}_{arg_id}'
                value = input[input_id]()

                kwargs[arg_id] = value

            try:
                df[new_col_name] = od_info['fn'](**kwargs)
            except Exception as e:
                ui.notification_show(ui.p(f'ERROR: {str(e)}'), duration=5, type='error')

        # Force invalidation by changing (just) the id of active_df. We also have
        # to keep the version of the df in the user's state in sync.
        dfcp = df.copy(deep=False)
        user_state().get_file(selected_file).df = dfcp
        active_df.set(dfcp)

        return


    @render.ui
    def od_function_inputs():
        sel_od_fns = input.sel_od_functions()
        if not sel_od_fns:
            return ui.div()

        accordions = []
        for sel_od in sel_od_fns:
            inputs = []
            # Some functions don't need extra arguments
            if not od.OD_IMPLEMENTED[sel_od]['args']:
                inputs.append(ui.p('No additional arguments needed.'))
            else:
                for arg_id, arg_label, arg_type in od.OD_IMPLEMENTED[sel_od]['args']:
                    input_id = f'{sel_od}_{arg_id}'
                    if arg_type == str:
                        inputs.append(ui.input_text(input_id, f'{arg_label}:', ''))
                    elif arg_type in (int, float):
                        inputs.append(ui.input_numeric(input_id, f'{arg_label}:', 0))
                    elif arg_type == 'date_unit':
                        inputs.append(ui.input_select(input_id, arg_label, od.DATE_STRS))

            accordions.append(
                ui.accordion_panel(sel_od, ui.layout_columns(*inputs, col_widths=[6, 6]))
            )

        return ui.accordion(*accordions, open=False)


    @render.data_frame
    @reactive.calc
    @print_func_name
    def explore_table():
        req(selected_file := input.sel_files_table())
        show_od_cols = input.checkbox_show_od_cols()
        
        file_obj = user_state().get_file(selected_file)
        df = file_obj.df



        # Filter out outlier detection columns if needed
        if not show_od_cols:
            od_cols = od.get_all_od_names(df)
            df = df[[c for c in df.columns if c not in od_cols]] 

        # Reorder columns so that date columns are shown first. Also, filter
        # out internal columns
        order = file_obj.date_cols + [c for c in df.columns if c not in file_obj.date_cols and c not in m.INTERNAL_COLS]
        return df[order]


    @reactive.effect
    @print_func_name('red')
    def populate_columns():
        req(selected_file := input.sel_files_columns())

        file_obj = user_state().get_file(selected_file)
        df = file_obj.df

        ui.update_selectize('sel_ph_col', choices=list(df.columns),)


    @reactive.effect
    @reactive.event(input.btn_ph_col_sel)
    @print_func_name('green')
    def mark_columns():
        req(selected_file := input.sel_files_columns())
        req(group := input.sel_ph_col())
        file_obj = user_state().get_file(selected_file)
        df = file_obj.df
        config = []
        for col in group:
            file_obj.ph_cols.append(col)
            config.append((
                od.pH_range_test,
                col,
                {}
            ))
        od_task.invoke(file_obj, config)
        


    @render_widget
    @print_func_name
    def plot_data():
        df = active_df()
        req(df)

        x_col = input.sel_x()
        y_col = input.sel_y()

        if df.empty or not all([x_col, y_col]):
            return px.scatter()

        # This happens when the file input value has been changed but the change
        # hasn't propagated to the inputs yet
        if x_col not in df or y_col not in df:
            req(False) # returning None will wipe out the graph

        jlog1(f'plot {x_col}/{y_col}')
        jlog1(f'{df[x_col].dtype}')

        # Set up the shape and color of markings, when relevant. We want each
        # outlier detection test to get a different shape+color combination.
        px_kwargs = {}
        if od_cols := od.get_od_names(df, x_col, y_col):
            px_kwargs['color'] = px_kwargs['symbol'] = categ_name = m.OUTLIER_TYPE

            df[categ_name] = df[od_cols].apply(util.get_true_first_column_name, axis=1)
            px_kwargs['category_orders'] = {
                categ_name: [m.PASS] + od_cols # keep 'pass' first
            }
        jlog1(f'od_cols: {od_cols}')

        # This will allow us to correlate selected data points with "df"
        df[m.IDX] = df.index

        # We need the graph as a widget so we can register callbacks. It might end up
        # being preferable to ditch plotly express and manually create the traces...
        fig = go.FigureWidget(px.scatter(
            df,
            x=x_col,
            y=y_col,
            custom_data=m.IDX,
            **px_kwargs
        ))

        od.prettify_column_names(fig, od_cols)

        jlog1(f'{len(fig.data)} trace(s)')
        for i, trace in enumerate(fig.data):
            trace.on_selection(partial(callback_data_selected, trace_num=i))

        fig.data[0].on_deselect(clear_selection) # we only need to clear the selection once

        return fig


    # Note about callbacks: Plotly catches and completely ignores exceptions within
    # callback functions. We catch and print them to make debugging possible.

    # This is executed on each trace in the graph (i.e. each set of labeled points,
    # like "pass", "test1", "test2", etc). Each trace has a 0-indexed list of indices -
    # these are the points on the graph that have been selected. We use the customdata
    # parameter set up for us to map these values to the values in the original DataFrame.
    @util.catch_errors
    @print_func_name
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

        jlog1(selected_points)
        jlog1()


    # Prevent manual flagging buttons from doing anything when data is deselected
    @util.catch_errors
    @print_func_name
    def clear_selection(trace, points) -> None:
        nonlocal selected_points
        selected_points = []


    @print_func_name
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

        jlog1(indices)
        jlog1(cols)
        if type(value) == bool:
            jlog1(value)
        else:
            jlog1(list(value))

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
        req(selected_points)

        with reactive.isolate():
            df = active_df()

        with reactive.isolate():
            x_col = input.sel_x()
            y_col = input.sel_y()
        manual_y_col = od.get_manual_col(y_col)

        if manual_y_col not in df:
            df[manual_y_col] = False

        if value:
            target_cols = [manual_y_col]
            new_values = [value for _ in selected_points]
        else:
            target_cols = od.get_od_names(df, x_col, y_col)
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


    @print_func_name
    def reset_flag_stacks():
        nonlocal redo_stack, undo_stack
        undo_stack = []
        redo_stack = []
        unemphasize_undo_button()
        unemphasize_redo_button()


    @print_func_name
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


    async def update_button_class(id, rm, add):
        await session.send_custom_message(
            'update_btn_class',
            {
                'id': id,
                'rm': rm,
                'add': add,
            }
        )
        
    # TODO: make sure these can't execute concurrently
    def emphasize_undo_button():
        asyncio.create_task(update_button_class('btn_undo_flag', 'btn-light', 'btn-warning'))
    def unemphasize_undo_button():
        asyncio.create_task(update_button_class('btn_undo_flag', 'btn-warning', 'btn-light'))
    def emphasize_redo_button():
        asyncio.create_task(update_button_class('btn_redo_flag', 'btn-light', 'btn-info'))
    def unemphasize_redo_button():
        asyncio.create_task(update_button_class('btn_redo_flag', 'btn-info', 'btn-light'))


    def get_export_file_name():
        selected_file = input.sel_files_export()
        req(selected_file)
        selected_ext = input.sel_export_format()
        custom_fname = input.text_export_custom_fname()

        if custom_fname:
            if selected_ext not in custom_fname:
                custom_fname += selected_ext
            return custom_fname

        return f'{util.remove_suffix(selected_file)}_screened{selected_ext}'


    @render.ui
    @print_func_name('green')
    def show_download_button():
        fname = get_export_file_name()
        jlog(fname)
        return ui.download_button('download_data', fname, class_='btn-primary')


    @render.download(
        filename=get_export_file_name
    )
    async def download_data(chunk_size=8192):
        df = active_df()
        req(df)

        selected_ext = input.sel_export_format()
        selected_export_options = input.export_settings()

        header = 'include_header' in selected_export_options

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

    #@render.image
    #def logo():
    #    img: ImgData = {'src': 'img/logo.png', 'width': '100%'}
    #    return img


app = App(app_ui.app_ui, server, debug=False)
