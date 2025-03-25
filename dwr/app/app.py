import sys
import math
import time
import inspect
from pathlib import Path
from functools import wraps
from pprint import pprint

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shiny.types import FileInfo, ImgData

from shinywidgets import output_widget, render_widget
import shinyswatch

import plotly.express as px

import od
import util
import app_state
import upload_util
from util import print_func_name, jlog, jlog1, jlog2


def req(variable):
    util.req(variable, output_fn=jlog)

app_ui = ui.page_sidebar(
            ui.sidebar(
                #ui.output_image('logo'),
                ui.p('Under construction'),
                open='closed',
            ),
            ui.navset_pill(
                ui.nav_panel('Upload',
                    ui.row(
                        ui.column(4,
                            ui.input_checkbox_group(
                                'upload_settings',
                                'Preprocessing settings:',
                                {
                                    'upload_nullify_hyphens': upload_util.upload_checkbox(
                                        'Nullify hyphen-only cells',
                                        'Update any values consisting of only hyphens (-) to contain no value. Then, attempt to convert any affected columns to a numeric type.'
                                    ),
                                },
                                selected=[
                                    'upload_nullify_hyphens',
                                ]
                            ),
                            ui.input_file('file1', 'Choose CSV File:', accept=['.csv'], multiple=False),
                            ui.output_ui('upload_text'),
                        ),
                        ui.column(8,
                            ui.output_data_frame('staged_table'),
                        ),
                    ),
                ),
                ui.nav_panel('Clean',
                    ui.p('Placeholder'),
                ),
                ui.nav_panel('Screen',
                    ui.row(
                        ui.column(5,
                            ui.row(
                                ui.input_select('sel_files_viz', 'File:', []),
                            ),
                            ui.row(
                                ui.input_select('sel_x', 'Date Column:', []),
                                ui.input_select('sel_y', 'Value Column:', []),
                            ),
                            #ui.row(
                            #    ui.input_select('sel_od', 'Outlier Detection Method:', list(od.OD_IMPLEMENTED.keys())),
                            #),
                            #ui.row(
                            #    ui.input_numeric('num_od_min', 'Min:', None),
                            #    ui.input_numeric('num_od_max', 'Max:', None),
                            #    ui.column(2,
                            #        ui.input_action_button('btn_od', 'Go', class_='btn-primary', style='height:100%; ')
                            #    ),
                            #),
                            ui.hr(),
                            ui.row(
                                ui.input_selectize(
                                    'sel_od_functions',
                                    'Outlier Detection:',
                                    choices=list(od.OD_IMPLEMENTED.keys()),
                                    multiple=True,
                                ),
                                ui.column(1,
                                    ui.input_action_button('btn_od', 'Go', class_='btn-primary', style='height:90%; ')
                                ),
                            ),
                            ui.output_ui('od_function_inputs'),
                        ),
                        ui.column(7,
                            output_widget('plot_data'),
                        ),
                    ),
                    ui.br(),
                ),
                ui.nav_spacer(),
                ui.nav_panel('Settings',
                    ui.br(),
                    shinyswatch.theme_picker_ui(),
                ),
                ui.nav_panel('Help',
                    ui.p('Placeholder'),
                ),
            ),
    #title='Tool', # takes up too much space
    window_title='Tool Prototype',
    theme=shinyswatch.theme.darkly, # default theme
)


def server(input: Inputs, output: Outputs, session: Session):

    # Enable theme picker
    shinyswatch.theme_picker_server()

    # Values just used in the 'upload' page
    upload_msg = reactive.Value(ui.p())
    upload_df = reactive.Value(pd.DataFrame())

    # Values just used in the 'visualize' page
    user_state = reactive.Value(app_state.State())
    active_df = reactive.Value(pd.DataFrame())

    @reactive.effect
    @print_func_name
    def read_file():
        file: list[FileInfo] | None = input.file1()
        req(file)

        fpath = Path(file[0]['datapath'])
        fname = file[0]['name']

        # Load file
        try:
            df = pd.read_csv(fpath)
        except Exception as e:
            upload_msg.set(upload_util.format_upload_error_msg(f'ERROR: could not load {fname}:', exception=e))
            return
        jlog1(f'loaded {fname}')

        #
        # Preprocess data if needed
        #
        selected_upload_options = input.upload_settings()

        if 'upload_nullify_hyphens' in selected_upload_options:
            fixed, attempted = upload_util.nullify_hyphens(df) # operates inplace on df
        else:
            fixed, attempted = None, None

        state = user_state()
        date_cols, num_cols = state.add_file(fname, df)

        ui.update_select('sel_files_viz', choices=state.get_filenames())

        upload_df.set(df)
        upload_msg.set(upload_util.format_upload_msg(
            f'Loaded <code>{fname}</code> successfully.',
            fixed,
            attempted,
            date_cols,
            num_cols,
        ))

        jlog1(f'read_file exit')


    @render.ui
    def upload_text():
        return upload_msg()


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
    @print_func_name
    def updateminmax():
        if not (y_col := input.sel_y()): #TODO: use req?
            jlog1(f'no ycol')
            return

        df = active_df()
        req(df)

        # This happens when the file has been changed but the change hasn't
        # propogated to the inputs yet
        if y_col not in df:
            jlog1(f'invalid col')
            return None

        min_y = int(df[y_col].min())
        max_y = int(df[y_col].max())
        ui.update_numeric('num_od_min', value=min_y)
        ui.update_numeric('num_od_max', value=max_y)


    @reactive.effect
    @reactive.event(input.btn_od)
    @print_func_name
    def do_outlier_detection():
        df = active_df()
        req(df)

        sel_od_fns = input.sel_od_functions()
        req(sel_od_fns)

        x_col = input.sel_x()
        req(x_col)
        y_col = input.sel_y()
        req(y_col)

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
                new_col_name = od.get_od_name(x_col, y_col, sel_od)
            else:
                data = df[x_col]
                new_col_name = od.get_od_name(x_col, None, sel_od)
            kwargs['ts'] = data

            jlog1(f'new_col_name: {new_col_name}')

            for arg_id, arg_label, arg_type in od_info['args']:
                input_id = f'{sel_od}_{arg_id}'
                value = input[input_id]()

                kwargs[arg_id] = value

            df[new_col_name] = od_info['fn'](**kwargs)

            # Force invalidation by just changing the id
            active_df.set(df.copy(deep=False))

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
    @print_func_name
    def staged_table():
        return upload_df()


    @render.data_frame
    @print_func_name
    def uploaded_table():
        df = active_df()
        if df is None:
            return None
        return df


    @render_widget
    @print_func_name
    def plot_data():
        df = active_df()
        req(df)

        x_col = input.sel_x()
        y_col = input.sel_y()

        if df.empty or not all([x_col, y_col]):
            #jlog1('plot empty')
            return px.scatter()

        # This happens when the file input value has been changed but the change
        # hasn't propagated to the inputs yet
        if x_col not in df or y_col not in df:
            #jlog1(f'invalid cols')
            req(False) # better than returning since returning None will wipe out the graph
            return None

        jlog1(f'plot {x_col}/{y_col}')
        jlog1(f'{df[x_col].dtype}')

        # Set up the shape and color of markings, when relevant. We want each
        # outlier detection test to get a different shape+color combination.
        px_kwargs = {}
        if od_cols := od.get_od_names(df, x_col, y_col):
            px_kwargs['color'] = px_kwargs['symbol'] = categ_name = 'Outlier Status'

            df[categ_name] = df[od_cols].apply(util.get_first_true_column_name, axis=1)
            px_kwargs['category_orders'] = {
                categ_name: [od.PASS] + od_cols # keep 'pass' first
            }
        jlog1(f'od_cols: {od_cols}')
            
        fig = px.scatter(
            df,
            #x=df[x_col],
            x=x_col,
            y=y_col,
            **px_kwargs
        )

        od.prettify_column_names(fig, od_cols)

        return fig

    #@render.image
    #def logo():
    #    img: ImgData = {'src': 'img/logo.png', 'width': '100%'}
    #    return img


app = App(app_ui, server, debug=False)
