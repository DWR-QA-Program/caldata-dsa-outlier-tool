import sys
import math
import time
import inspect
from pathlib import Path
from functools import wraps

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shiny.types import FileInfo

from shinywidgets import output_widget, render_widget
import shinyswatch

import plotly.express as px

import od
import util
import app_state

LOG_MSG = 0


# TODO: increase level as call stack grows in depth
def print_func_name(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        jlog(f'{func.__name__}')
        return func(*args, **kwargs)
    return wrapper


def jlog(msg, level=0):
    print(f'JLO: {chr(9)*level}{msg}')

    global LOG_MSG
    LOG_MSG += 1
    if LOG_MSG > 500:
        raise RuntimeError('something has gone wrong')


def jlog1(msg):
    return jlog(msg, level=1)
def jlog2(msg):
    return jlog(msg, level=2)


def req(variable):
    util.req(variable, output_fn=jlog)


# TODO: this, manually 
od_fn = [name for name, _ in inspect.getmembers(od, inspect.isfunction)]


app_ui = ui.page_fixed (
    ui.layout_sidebar(
        ui.sidebar(
            ui.input_file('file1', 'Choose CSV File:', accept=['.csv'], multiple=False),
            #open="closed",
        ),
        #ui.br(),
        ui.row(
            ui.input_select('sel_files', 'File:', []),
        ),
        ui.row(
            ui.input_select('sel_x', 'X:', []),
            ui.input_select('sel_y', 'Y:', []),
        ),
        ui.row(
            ui.column(9, output_widget('plot_data')),
            #ui.column(3, output_widget('map_data')),
        ),

        ui.row(
                ui.input_select('sel_od', 'Outlier Detection Method:', od_fn),
        ),
        ui.row(
            #ui.input_slider('sld_od', 'Bounds:', min=0, max=100, value=[0,100]),
                ui.input_numeric('num_od_min', 'Min:', None),
                ui.input_numeric('num_od_max', 'Max:', None),
            ui.column(2,
                #ui.input_action_button('btn_od', 'Go', class_='btn-primary', style='position:absolute; bottom:-1; ')
                ui.input_action_button('btn_od', 'Go', class_='btn-primary', style='height:100%; ')
            ),
        ),
        ui.br(),
        ui.accordion(
            ui.accordion_panel('Tabular View',
                ui.output_data_frame('uploaded_table'),
            ),
            open=False
        ),
        ui.br(),
        ui.br(),
    ),
    title='Tool Prototype',
    theme=shinyswatch.theme.darkly,
)


def server(input: Inputs, output: Outputs, session: Session):
    # This isn't really used as a reactive value
    user_state = reactive.Value(app_state.State())
    active_df = reactive.Value(pd.DataFrame())


    @reactive.effect
    @print_func_name
    def read_file():
        file: list[FileInfo] | None = input.file1()

        if file is None:
            jlog1('no file')
            return

        fpath = Path(file[0]['datapath'])
        fname = file[0]['name']


        df = pd.read_csv(fpath)
        jlog1(f'loaded {fname}')

        state = user_state()
        state.add_file(fname, df)

        ui.update_select('sel_files', choices=state.get_filenames())
        jlog1(f'read_file exit')


    #@reactive.calc
    #@print_func_name
    #def get_active_df():
    #    if not (selected_file := input.sel_files()):
    #        jlog1(f'no selected_file')
    #        return None
    #    return user_state().get_file(selected_file).df
        


    @reactive.effect
    @print_func_name
    def update_x_and_y_cols():
        if not (selected_file := input.sel_files()):
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
        if not (selected_file := input.sel_files()):
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
        if not (selected_file := input.sel_files()):
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
        #if not (selected_file := input.sel_files()):
        #    jlog1(f'no selected_file')
        #    return
        if not (y_col := input.sel_y()):
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
        #if not (selected_file := input.sel_files()):
        #    jlog1(f'no selected_file')
        #    return
        if not (y_col := input.sel_y()):
            jlog1(f'no ycol')
            return

        df = active_df()
        req(df)

        y_min = input.num_od_min()
        y_max = input.num_od_max()

        ret = od.gross_range_test(df[y_col], (y_min, y_max))
        new_col_name = util.get_od_name(y_col)
        df[new_col_name] = ret[od.default_od_col_name]

        # Force invalidation by just changing the id
        active_df.set(df.copy(deep=False))


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
            jlog1('plot empty')
            return px.scatter()

        # This happens when the file has been changed but the change hasn't
        # propogated to the inputs yet
        if x_col not in df or y_col not in df:
            jlog1(f'invalid cols')
            req(False)
            return None

        jlog1(f'plot {x_col}')
        jlog1(f'plot {y_col}')

        od_col = util.get_od_name(y_col)

        color = None
        color_discrete_map = None
        if od_col in df:
            color = od_col
            color_discrete_map = {True: 'orange', False: 'blue'}


        fig = px.scatter(df, x=x_col, y=y_col, color=color, color_discrete_map=color_discrete_map)
        #fig.update_layout(xaxis_type='DATE')

        return fig


    @render_widget
    def map_data():
        jlog('map_data')
        cities = [
            {'name': 'Los Angeles', 'lat': 34.0522, 'lon': -118.2437},
            {'name': 'San Francisco', 'lat': 37.7749, 'lon': -122.4194},
            {'name': 'San Diego', 'lat': 32.7157, 'lon': -117.1611},
            {'name': 'Sacramento', 'lat': 38.5816, 'lon': -121.4944},
            {'name': 'Fresno', 'lat': 36.7378, 'lon': -119.7871}
        ]

        fig = px.scatter_geo(
            cities, 
            lat=[city['lat'] for city in cities], 
            lon=[city['lon'] for city in cities], 
            text=[city['name'] for city in cities],
            title='CA Cities',
            scope='usa'
        )

        # focus on CA
        fig.update_layout(
            geo=dict(
                center={'lat': 36.7783, 'lon': -119.4179},
                projection_scale=5 # adjusts zoom
            )
        )
        return fig


app = App(app_ui, server, debug=False)
