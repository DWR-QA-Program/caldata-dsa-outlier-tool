# Contains functions related to allowing the user to plot their data.
from functools import partial

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objs as go

from . import m, od, schema, util
from .util import jlog1


# Saves data to enable undo/redo buttons above the plot
class PlotState:
    def __init__(self):
        # Track the indices of points that the user has selected on the graph
        self.selected_points = []

        self.undo_stack = []
        self.redo_stack = []

        self.x_range = None
        self.y_range = None

    def get_selected_points(self):
        return self.selected_points

    def set_selected_points(self, points):
        self.selected_points = points

    def append_selected_points(self, points):
        self.selected_points = np.append(self.selected_points, points)

    def reset_selected_points(self):
        self.selected_points = []

    def undo_stack_is_empty(self):
        return len(self.undo_stack) == 0

    def redo_stack_is_empty(self):
        return len(self.redo_stack) == 0

    def add_undo(self, sel, target, prev, new):
        self.undo_stack.append((sel, target, prev, new))

    def add_redo(self, sel, target, prev, new):
        self.redo_stack.append((sel, target, prev, new))

    def undo(self):
        sel, cols, prev, new = self.undo_stack.pop()  # raises IndexError when empty
        self.add_redo(sel, cols, prev, new)
        return sel, cols, prev

    def redo(self):
        sel, cols, prev, new = self.redo_stack.pop()  # raises IndexError when empty
        self.add_undo(sel, cols, prev, new)
        return sel, cols, new

    def set_zoom(self, x, y):
        self.x_range = x
        self.y_range = y

    def get_zoom(self):
        return self.x_range, self.y_range

    def reset_undo(self):
        self.undo_stack = []

    def reset_redo(self):
        self.redo_stack = []

    def reset_stacks(self):
        self.reset_undo()
        self.reset_redo()

    def reset_zoom(self):
        self.x_range = None
        self.y_range = None


def plot_data(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    schema: schema.Schema,
    plot_state: PlotState,
):
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
            categ_name: [m.PASS, *od_cols]  # keep 'pass' first
        }

        # Create column to show (on hover) what tests failed for a data point
        renames = od.get_od_col_renames(od_cols)
        df[m.FAILURES] = df[od_cols].apply(util.get_all_failures, axis=1, renames=renames)
        px_kwargs['hover_data'] = [m.FAILURES]

    jlog1(f'od_cols: {od_cols}')

    # This will allow us to correlate selected data points with "df"
    df[m.IDX] = df.index

    # Add unit to y-axis label
    if (
        schema is not None
        and (col_obj := schema.get(y_col, None)) is not None
        and col_obj.units is not None
    ):
        px_kwargs['labels'] = {y_col: f'{y_col} ({col_obj.units})'}

    # We need the graph as a widget so we can register callbacks.
    fig = go.FigureWidget(px.scatter(df, x=x_col, y=y_col, custom_data=m.IDX, **px_kwargs))

    # Set the "modebar" at the top right of the plot to always display, rather
    # than only display on hover.
    if not hasattr(fig, '_config') or fig._config is None:
        fig._config = {}
    fig._config['displayModeBar'] = True
    fig._config['scrollZoom'] = True

    # Rename outlier detection columns so they display nicely in the legend.
    od.apply_renames(fig, renames)

    # Set up callbacks for when data is selected
    for i, trace in enumerate(fig.data):
        trace.on_selection(partial(callback_data_selected, trace_num=i, plot_state=plot_state))

    # Set up callback for when data is deselected - this only needs to happen
    # for one of the traces.
    fig.data[0].on_deselect(partial(callback_clear_selection, plot_state=plot_state))

    # Make sure that we capture changes to the zoom (layout) of the plot
    fig.observe(partial(capture_layout, plot_state=plot_state), names=['_js2py_layoutDelta'], type='change')

    # Apply the saved zoom
    xrange, yrange = plot_state.get_zoom()
    if xrange and yrange:
        fig.update_xaxes(range=xrange)
        fig.update_yaxes(range=yrange)

    return fig


# Note about plot callbacks: Plotly catches and completely ignores exceptions within
# callback functions. We intercept and print them to make debugging possible.


# This is executed on each trace in the graph (i.e. each set of labeled points,
# like "pass", "test1", "test2", etc). Each trace has a 0-indexed list of indices -
# these are the points on the graph that have been selected. We use the customdata
# parameter set up for us to map these values to the values in the original DataFrame.
@util.catch_errors
def callback_data_selected(trace, points, selector, trace_num: int, plot_state) -> None:
    jlog1(f'trace #{trace_num}: {trace.legendgroup}')

    # The shape of customdata is a list of lists, each with 1 element. Get
    # that 1 element for selected indices.
    df_indices = trace.customdata[points.point_inds, 0]

    if trace_num == 0:
        plot_state.set_selected_points(df_indices)
    else:
        plot_state.append_selected_points(df_indices)


# Prevent manual flagging buttons from doing anything when data is deselected
@util.catch_errors
def callback_clear_selection(trace, points, plot_state) -> None:
    plot_state.reset_selected_points()


@util.catch_errors
def capture_layout(change, plot_state):
    layout = change.owner.layout
    plot_state.set_zoom(layout.xaxis.range, layout.yaxis.range)
