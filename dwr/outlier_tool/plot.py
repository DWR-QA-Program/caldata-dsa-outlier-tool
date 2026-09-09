# Contains functions related to allowing the user to plot their data.
from functools import partial

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objs as go

from . import m, od, schema, util
from .util import jlog1

MULTIPLE_TESTS = 'Multiple tests'
MANUALLY_FLAGGED = 'Manually flagged'

PASS_COLOR = '#999999'
MULTIPLE_COLOR = '#a65628'
MANUAL_COLOR = '#f781bf'

# to help plot points look better
def hex_to_rgba(hex_color, alpha):
    hex_color = hex_color.lstrip('#')
    r, g, b = (
        int(hex_color[i:i + 2], 16)
        for i in (0, 2, 4)
    )
    return f'rgba({r}, {g}, {b}, {alpha})'

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
        self.selected_points = np.append(
            self.selected_points,
            points,
        )

    def reset_selected_points(self):
        self.selected_points = []

    def undo_stack_is_empty(self):
        return len(self.undo_stack) == 0

    def redo_stack_is_empty(self):
        return len(self.redo_stack) == 0

    def add_undo(
        self,
        analyte,
        prev_state,
        new_state,
    ):
        self.undo_stack.append(
            (
                analyte,
                prev_state,
                new_state,
            )
        )

    def add_redo(
        self,
        analyte,
        prev_state,
        new_state,
    ):
        self.redo_stack.append(
            (
                analyte,
                prev_state,
                new_state,
            )
        )

    def undo(self):
        analyte, prev, new = self.undo_stack.pop()
        self.add_redo(
            analyte,
            prev,
            new,
        )
        return analyte, prev

    def redo(self):
        analyte, prev, new = self.redo_stack.pop()
        self.add_undo(
            analyte,
            prev,
            new,
        )
        return analyte, new

    def set_zoom(
        self,
        x,
        y,
    ):
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

# helper
def _get_test_info(method_key):
    for test_key, test_info in od.OD_TESTS.items():
        if method_key in test_info['methods']:
            return test_key, test_info

    return None, {
        'label': method_key,
        'color': '#6c757d',
    }

def _build_flag_columns(
    df,
    y_col,
    file_obj,
):
    labels = {}

    if file_obj is None:
        return labels

    for method_key, entry in file_obj.get_od_results_for(
        y_col
    ).items():
        if (
            entry['error'] is not None
            or entry['result'] is None
        ):
            continue

        _, test_info = _get_test_info(
            method_key
        )

        label = test_info['label']

        result = (
            entry['result']
            .reindex(df.index)
            .fillna(False)
            .astype(bool)
        )

        if label in labels:
            labels[label] = (
                labels[label] | result
            )
        else:
            labels[label] = result

    # Overrides let the user clear a test-generated flag.
    overrides = file_obj.get_flag_overrides(
        y_col
    )

    if overrides:
        cleared = pd.Series(
            df.index.isin(
                list(overrides)
            ),
            index=df.index,
        )

        for name in labels:
            labels[name] = (
                labels[name]
                & ~cleared
            )

    # Manual flags are kept separately.
    manual = file_obj.get_manual_flags(
        y_col
    )

    if manual:
        labels[MANUALLY_FLAGGED] = pd.Series(
            df.index.isin(
                list(manual)
            ),
            index=df.index,
        )

    return labels


def _add_flag_display_columns(
    df,
    labels,
):
    if not labels:
        return None

    flags = (
        pd.DataFrame(
            labels,
            index=df.index,
        )
        .fillna(False)
        .astype(bool)
    )

    test_names = [
        name
        for name in flags.columns
        if name != MANUALLY_FLAGGED
    ]

    if test_names:
        test_flags = flags[test_names]
        n_test_flags = test_flags.sum(
            axis=1
        )
    else:
        test_flags = pd.DataFrame(
            index=df.index
        )
        n_test_flags = pd.Series(
            0,
            index=df.index,
            dtype='int64',
        )

    category = pd.Series(
        m.PASS,
        index=df.index,
        dtype='object',
    )

    # Exactly one test failed.
    single_test = n_test_flags.eq(1)

    if single_test.any():
        category.loc[single_test] = (
            test_flags
            .loc[single_test]
            .idxmax(axis=1)
        )

    # More than one test failed.
    multiple_tests = n_test_flags.gt(1)

    category.loc[
        multiple_tests
    ] = MULTIPLE_TESTS

    # Manual gets its own category only when no
    # automated test already flagged the point.
    if MANUALLY_FLAGGED in flags.columns:
        manual_only = (
            n_test_flags.eq(0)
            & flags[MANUALLY_FLAGGED]
        )

        category.loc[
            manual_only
        ] = MANUALLY_FLAGGED

    df[m.OUTLIER_TYPE] = category

    # Build hover text by looping over columns,
    # rather than applying a Python function row by row.
    failure_text = pd.Series(
        '',
        index=df.index,
        dtype='object',
    )

    for name in flags.columns:
        mask = flags[name]

        if not mask.any():
            continue

        current = failure_text.loc[
            mask
        ]

        failure_text.loc[
            mask
        ] = np.where(
            current.eq(''),
            name,
            current + '; ' + name,
        )

    df[m.FAILURES] = (
        failure_text
        .mask(
            failure_text.eq(''),
            'None',
        )
    )

    category_order = [
        m.PASS,
        *test_names,
    ]

    if multiple_tests.any():
        category_order.append(
            MULTIPLE_TESTS
        )

    if (
        MANUALLY_FLAGGED in flags.columns
        and (
            category == MANUALLY_FLAGGED
        ).any()
    ):
        category_order.append(
            MANUALLY_FLAGGED
        )

    return category_order

def plot_data(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    schema: schema.Schema,
    plot_state: PlotState,
    file_obj=None,
):
    jlog1(f'plot {x_col}/{y_col}')

    px_kwargs = {}

    # In long format, y_col is the analyte name.
    # The actual y values live in value_col.
    if file_obj is not None and file_obj.is_long:
        df = df.loc[
            file_obj.get_analyte_mask(y_col)
        ]
        plot_y = file_obj.value_col
    else:
        plot_y = y_col

    df = df.copy(deep=False)

    if (
        df.empty
        or x_col not in df
        or plot_y not in df
    ):
        return go.FigureWidget()

    jlog1(f'{df[x_col].dtype}')

    labels = _build_flag_columns(
        df,
        y_col,
        file_obj,
    )

    color_map = {
        m.PASS: PASS_COLOR,
        MULTIPLE_TESTS: MULTIPLE_COLOR,
        MANUALLY_FLAGGED: MANUAL_COLOR,
    }

    for test_info in od.OD_TESTS.values():
        color_map[test_info['label']] = test_info.get(
            'color',
            '#6c757d',
        )

    category_order = _add_flag_display_columns(
        df,
        labels,
    )

    if category_order is not None:
        symbol_map = dict.fromkeys(
            category_order,
            'circle',
        )

        if MULTIPLE_TESTS in category_order:
            symbol_map[MULTIPLE_TESTS] = 'diamond'

        if MANUALLY_FLAGGED in category_order:
            symbol_map[MANUALLY_FLAGGED] = 'square'

        px_kwargs['color'] = m.OUTLIER_TYPE
        px_kwargs['symbol'] = m.OUTLIER_TYPE
        px_kwargs['color_discrete_map'] = color_map
        px_kwargs['symbol_map'] = symbol_map

        px_kwargs['category_orders'] = {
            m.OUTLIER_TYPE: category_order,
        }

        px_kwargs['hover_data'] = {
            m.FAILURES: True,
        }

    jlog1(f'flags: {list(labels)}')

    # Preserve original dataframe indices so selected
    # Plotly points can map back to source rows.
    df[m.IDX] = df.index

    # Add unit to y-axis label.
    if (
        schema is not None
        and (
            col_obj := schema.get(
                plot_y,
                None,
            )
        ) is not None
        and col_obj.units is not None
    ):
        px_kwargs['labels'] = {
            plot_y: f'{plot_y} ({col_obj.units})',
        }

    fig = go.FigureWidget(
        px.scatter(
            df,
            x=x_col,
            y=plot_y,
            custom_data=m.IDX,
            render_mode='webgl',
            **px_kwargs,
        )
    )

    for trace in fig.data:
        trace.hovertemplate = trace.hovertemplate.replace('=', ': ')

    # Passing points visually recede; flagged points stand out.
    for trace in fig.data:
        base_color = color_map.get(
            trace.name,
            '#6c757d',
        )

        if trace.name == m.PASS:
            fill_alpha = 0.35
            line_width = 1
        else:
            fill_alpha = 0.45
            line_width = 1.5

        trace.update(
            marker={
                'size': 7,
                'color': hex_to_rgba(
                    base_color,
                    fill_alpha,
                ),
                'line': {
                    'color': base_color,
                    'width': line_width,
                },
            }
        )

    fig.update_layout(
        template='plotly_white',
        dragmode='pan',
        hovermode='closest',
        margin={
            'l': 60,
            'r': 20,
            't': 20,
            'b': 55,
        },
        legend={
            'title': {
                'text': 'Point status',
            },
            'y': 0.93,
            'yanchor': 'top',
        },
    )

    fig.update_xaxes(
        showgrid=True,
        zeroline=False,
    )

    fig.update_yaxes(
        showgrid=True,
        zeroline=False,
    )

    if (
        not hasattr(fig, '_config')
        or fig._config is None
    ):
        fig._config = {}

    fig._config.update(
        {
            'displayModeBar': True,
            'displaylogo': False,
            'scrollZoom': True,
            'modeBarButtonsToRemove': [
                'zoomIn2d',
                'zoomOut2d',
                'autoScale2d',
                'toggleSpikelines',
                'hoverClosestCartesian',
                'hoverCompareCartesian',
                'toImage',
            ],
        }
    )

    # Selection callbacks.
    for i, trace in enumerate(fig.data):
        trace.on_selection(
            partial(
                callback_data_selected,
                trace_num=i,
                plot_state=plot_state,
            )
        )

    if fig.data:
        fig.data[0].on_deselect(
            partial(
                callback_clear_selection,
                plot_state=plot_state,
            )
        )

    # Track zoom changes.
    fig.observe(
        partial(
            capture_layout,
            plot_state=plot_state,
        ),
        names=['_js2py_layoutDelta'],
        type='change',
    )

    # Reapply stored zoom.
    xrange, yrange = plot_state.get_zoom()

    if xrange and yrange:
        fig.update_xaxes(
            range=xrange
        )
        fig.update_yaxes(
            range=yrange
        )

    return fig


# Plotly catches exceptions inside callbacks,
# so these wrappers surface them.


@util.catch_errors
def callback_data_selected(
    trace,
    points,
    selector,
    trace_num: int,
    plot_state,
) -> None:
    jlog1(
        f'trace #{trace_num}: '
        f'{trace.legendgroup}'
    )

    df_indices = (
        trace.customdata[
            points.point_inds,
            0,
        ]
    )

    if trace_num == 0:
        plot_state.set_selected_points(
            df_indices
        )
    else:
        plot_state.append_selected_points(
            df_indices
        )


@util.catch_errors
def callback_clear_selection(
    trace,
    points,
    plot_state,
) -> None:
    plot_state.reset_selected_points()


@util.catch_errors
def capture_layout(
    change,
    plot_state,
):
    layout = change.owner.layout

    plot_state.set_zoom(
        layout.xaxis.range,
        layout.yaxis.range,
    )