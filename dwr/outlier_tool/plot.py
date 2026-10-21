# Contains functions related to allowing the user to plot their data.
#
# The Review plot is a plain plotly Figure sent to the browser as JSON and drawn
# with Plotly.react (see the 'review_plot' message handler in the JS util file).
# Pan, zoom and hover stay in the browser. The browser sends back:
#   - box/lasso selections, as `review_plot_selected`
#   - the visible range after a zoom/pan, as `review_plot_view`
#
# Large datasets: flagged points are always drawn in full. Passing points are drawn
# in full only when the view holds DETAIL_LIMIT or fewer of them; otherwise a grid
# sample is drawn (one point per small cell of the plot, so spikes and the shape of
# the data survive) and the user is told to zoom in.
#
# The work is split in two:
#   build_plot_data()  heavy, view-independent; cached by app.py
#   make_figure()      cheap; re-run whenever the visible range changes
import numpy as np
import pandas as pd
import plotly.graph_objs as go

from . import m, od, schema
from .util import jlog1

MULTIPLE_TESTS = 'Multiple tests'
MANUALLY_FLAGGED = 'Manually flagged'

PASS_COLOR = '#999999'
MULTIPLE_COLOR = '#a65628'
MANUAL_COLOR = '#f781bf'

# Most passing points drawn at full detail. 20k was tested smooth; raise it if
# your users' machines handle more.
DETAIL_LIMIT = 20_000
# Grid used to sample passing points inside the view when it holds too many
# (columns, rows). columns * rows is the most points it can return.
DETAIL_GRID = (400, 50)
# Coarser grid for passing points outside the full-detail region, so the rest of
# the data is still visible while panning.
OVERVIEW_GRID = (250, 20)
# Load full detail this far past each edge of the view (fraction of view size),
# so small pans don't show empty space before the next update arrives.
EXPAND = 0.5

PLOT_CONFIG = {
    'displayModeBar': True,
    'displaylogo': False,
    'scrollZoom': True,
    'responsive': True,
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

# to help plot points look better
def hex_to_rgba(hex_color, alpha):
    hex_color = hex_color.lstrip('#')
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    return f'rgba({r}, {g}, {b}, {alpha})'


# Selection and undo/redo state for the Review tab. Zoom is not tracked here:
# layout.uirevision makes the browser keep it across redraws.
class PlotState:
    def __init__(self):
        # Indices (dataframe row labels) of points the user selected on the graph
        self.selected_points = []
        self.undo_stack = []
        self.redo_stack = []

    def get_selected_points(self):
        return self.selected_points

    def set_selected_points(self, points):
        self.selected_points = points

    def reset_selected_points(self):
        self.selected_points = []

    def undo_stack_is_empty(self):
        return len(self.undo_stack) == 0

    def redo_stack_is_empty(self):
        return len(self.redo_stack) == 0

    def add_undo(self, analyte, prev_state, new_state):
        self.undo_stack.append((analyte, prev_state, new_state))

    def add_redo(self, analyte, prev_state, new_state):
        self.redo_stack.append((analyte, prev_state, new_state))

    def undo(self):
        analyte, prev, new = self.undo_stack.pop()
        self.add_redo(analyte, prev, new)
        return analyte, prev

    def redo(self):
        analyte, prev, new = self.redo_stack.pop()
        self.add_undo(analyte, prev, new)
        return analyte, new

    def reset_undo(self):
        self.undo_stack = []

    def reset_redo(self):
        self.redo_stack = []

    def reset_stacks(self):
        self.reset_undo()
        self.reset_redo()


# helper
def _get_test_info(method_key):
    for test_key, test_info in od.OD_TESTS.items():
        if method_key in test_info['methods']:
            return test_key, test_info

    return None, {
        'label': method_key,
        'color': '#6c757d',
    }


def _build_flag_columns(df, y_col, file_obj):
    labels = {}

    if file_obj is None:
        return labels

    for method_key, entry in file_obj.get_od_results_for(y_col).items():
        if entry['error'] is not None or entry['result'] is None:
            continue

        _, test_info = _get_test_info(method_key)
        label = test_info['label']
        result = entry['result'].reindex(df.index).fillna(False).astype(bool)

        if label in labels:
            labels[label] = labels[label] | result
        else:
            labels[label] = result

    # Overrides let the user clear a test-generated flag.
    overrides = file_obj.get_flag_overrides(y_col)

    if overrides:
        cleared = pd.Series(df.index.isin(list(overrides)), index=df.index)
        for name, value in labels.items():
            labels[name] = value & ~cleared

    # Manual flags are kept separately.
    manual = file_obj.get_manual_flags(y_col)

    if manual:
        labels[MANUALLY_FLAGGED] = pd.Series(df.index.isin(list(manual)), index=df.index)

    return labels


def _add_flag_display_columns(df, labels):
    if not labels:
        return None

    flags = pd.DataFrame(labels, index=df.index).fillna(False).astype(bool)

    test_names = [name for name in flags.columns if name != MANUALLY_FLAGGED]

    if test_names:
        test_flags = flags[test_names]
        n_test_flags = test_flags.sum(axis=1)
    else:
        test_flags = pd.DataFrame(index=df.index)
        n_test_flags = pd.Series(0, index=df.index, dtype='int64')

    category = pd.Series(m.PASS, index=df.index, dtype='object')

    # Exactly one test failed.
    single_test = n_test_flags.eq(1)
    if single_test.any():
        category.loc[single_test] = test_flags.loc[single_test].idxmax(axis=1)

    # More than one test failed.
    multiple_tests = n_test_flags.gt(1)
    category.loc[multiple_tests] = MULTIPLE_TESTS

    # Manual gets its own category only when no automated test already flagged the point.
    if MANUALLY_FLAGGED in flags.columns:
        manual_only = n_test_flags.eq(0) & flags[MANUALLY_FLAGGED]
        category.loc[manual_only] = MANUALLY_FLAGGED

    df[m.OUTLIER_TYPE] = category

    # Build hover text by looping over columns rather than row by row.
    failure_text = pd.Series('', index=df.index, dtype='object')

    for name in flags.columns:
        mask = flags[name]
        if not mask.any():
            continue
        current = failure_text.loc[mask]
        failure_text.loc[mask] = np.where(current.eq(''), name, current + '; ' + name)

    df[m.FAILURES] = failure_text.mask(failure_text.eq(''), 'None')

    category_order = [m.PASS, *test_names]

    if multiple_tests.any():
        category_order.append(MULTIPLE_TESTS)

    if MANUALLY_FLAGGED in flags.columns and (category == MANUALLY_FLAGGED).any():
        category_order.append(MANUALLY_FLAGGED)

    return category_order


def _color_map():
    color_map = {
        m.PASS: PASS_COLOR,
        MULTIPLE_TESTS: MULTIPLE_COLOR,
        MANUALLY_FLAGGED: MANUAL_COLOR,
    }
    for test_info in od.OD_TESTS.values():
        color_map[test_info['label']] = test_info.get('color', '#6c757d')
    return color_map


def _plot_x(series: pd.Series):
    """Return (float values, is_date) for the x axis.

    Dates become epoch milliseconds on a date-typed axis: one compact numeric array
    instead of a string per point. Hover labels still show formatted dates.
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        if series.dt.tz is not None:
            series = series.dt.tz_localize(None)  # keep wall-clock time
        ms = (series - pd.Timestamp(0)) / pd.Timedelta(milliseconds=1)
        return ms.to_numpy(dtype=float), True

    return pd.to_numeric(series, errors='coerce').to_numpy(dtype=float), False


# --- sampling helpers --------------------------------------------------------


def _grid_sample(x, y, grid, x_range=None, y_range=None):
    """Positions of one point per occupied grid cell.

    Isolated points (spikes, outliers) sit in their own cells, so they are always
    kept; dense areas are thinned to one point per cell.
    """
    if len(x) == 0:
        return np.empty(0, dtype=np.int64)

    nx, ny = grid
    x0, x1 = x_range if x_range else (x.min(), x.max())
    y0, y1 = y_range if y_range else (y.min(), y.max())

    gx = np.clip(((x - x0) / ((x1 - x0) or 1) * nx).astype(np.int64), 0, nx - 1)
    gy = np.clip(((y - y0) / ((y1 - y0) or 1) * ny).astype(np.int64), 0, ny - 1)

    _, first = np.unique(gx * ny + gy, return_index=True)
    return first


def _axis_range(view, axis):
    lo, hi = view.get(f'{axis}0'), view.get(f'{axis}1')
    if lo is None or hi is None:
        return None
    return (min(lo, hi), max(lo, hi))


def _in_box(x, y, view):
    mask = np.ones(len(x), dtype=bool)
    if xr := _axis_range(view, 'x'):
        mask &= (x >= xr[0]) & (x <= xr[1])
    if yr := _axis_range(view, 'y'):
        mask &= (y >= yr[0]) & (y <= yr[1])
    return mask


def _expand(view, frac=EXPAND):
    out = dict(view)
    for axis in ('x', 'y'):
        if r := _axis_range(view, axis):
            pad = (r[1] - r[0]) * frac
            out[f'{axis}0'], out[f'{axis}1'] = r[0] - pad, r[1] + pad
    return out


# --- figure building ---------------------------------------------------------


def build_plot_data(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    schema: schema.Schema,
    file_obj=None,
    x_label: str | None = None,
) -> dict | None:
    """Everything about the plot that doesn't depend on the zoom level.

    Returns None when there is nothing to plot.
    """
    jlog1(f'plot {x_col}/{y_col}')

    # In long format, y_col is the analyte name. The actual y values live in value_col.
    if file_obj is not None and file_obj.is_long:
        df = df.loc[file_obj.get_analyte_mask(y_col)]
        plot_y = file_obj.value_col
    else:
        plot_y = y_col

    if df.empty or x_col not in df or plot_y not in df:
        return None

    df = df.copy(deep=False)

    labels = _build_flag_columns(df, y_col, file_obj)
    category_order = _add_flag_display_columns(df, labels)

    if category_order is None:
        category = np.full(len(df), m.PASS, dtype=object)
        failures = None
        category_order = [m.PASS]
    else:
        category = df[m.OUTLIER_TYPE].to_numpy()
        failures = df[m.FAILURES].to_numpy()

    jlog1(f'flags: {list(labels)}')

    x, x_is_date = _plot_x(df[x_col])
    y = pd.to_numeric(df[plot_y], errors='coerce').to_numpy(dtype=float)

    # Row labels, so selections map back to source rows. int32 keeps the array
    # binary-encodable for plotly.js (it has no int64 typed array).
    idx = np.asarray(df.index, dtype=np.int32)

    # Axis labels
    x_label = x_label or x_col
    y_label = y_col
    if schema is not None and (col_obj := schema.get(plot_y, None)) is not None and col_obj.units:
        y_label = f'{y_col} ({col_obj.units})'

    # Flagged points: always drawn in full.
    flagged = []
    for name in category_order:
        if name == m.PASS:
            continue
        mask = category == name
        if not mask.any():
            continue
        flagged.append(
            {
                'name': str(name),
                'x': x[mask],
                'y': y[mask],
                'idx': idx[mask],
                'text': failures[mask],
            }
        )

    # Passing points: only ones that can be drawn, sorted by x.
    is_pass = (category == m.PASS) & np.isfinite(x) & np.isfinite(y)
    px, py, pidx = x[is_pass], y[is_pass], idx[is_pass]
    order = np.argsort(px, kind='stable')
    px, py, pidx = px[order], py[order], pidx[order]

    large = len(px) > DETAIL_LIMIT

    data = {
        'x_is_date': x_is_date,
        'x_label': x_label,
        'y_label': y_label,
        'flagged': flagged,
        'pass_x': px,
        'pass_y': py,
        'pass_idx': pidx,
        'large': large,
        'overview': None,
        'sampled_all': None,
    }

    if large:
        data['overview'] = _grid_sample(px, py, OVERVIEW_GRID)
        data['sampled_all'] = _grid_sample(px, py, DETAIL_GRID)

    jlog1(f'passing points: {len(px)}, large: {large}')
    return data


def _choose_pass_points(data, view):
    """Positions (into pass_x/pass_y) of the passing points to draw, plus a status dict."""
    px, py = data['pass_x'], data['pass_y']
    n = len(px)

    status = {
        'large': data['large'],
        'sampled': False,
        'shown': n,
        'in_view': n,
    }

    if not data['large']:
        return np.arange(n), status

    if view is None:
        keep = data['sampled_all']
        status.update(sampled=True, shown=len(keep))
        return keep, status

    in_view = _in_box(px, py, view)
    n_view = int(in_view.sum())
    status.update(in_view=n_view, shown=n_view)

    expanded = _in_box(px, py, _expand(view))

    if expanded.sum() <= DETAIL_LIMIT:
        # Full detail in and around the view
        region = expanded
        detail = np.flatnonzero(expanded)
    elif n_view <= DETAIL_LIMIT:
        # Full detail in the view only
        region = in_view
        detail = np.flatnonzero(in_view)
    else:
        # Too many even in the view: sample at screen resolution
        region = in_view
        pos = np.flatnonzero(in_view)
        detail = pos[
            _grid_sample(
                px[pos],
                py[pos],
                DETAIL_GRID,
                _axis_range(view, 'x'),
                _axis_range(view, 'y'),
            )
        ]
        status.update(sampled=True, shown=len(detail))

    # Coarse sample of everything else, so the rest of the data stays visible
    overview = data['overview']
    outside = overview[~region[overview]]

    return np.concatenate([detail, outside]), status


def _scatter(name, uid, x, y, idx, text, hovertemplate, color, is_pass, symbol):
    return go.Scattergl(
        x=x,
        y=y,
        customdata=idx,
        text=text,
        hovertemplate=hovertemplate + '<extra></extra>',
        mode='markers',
        name=name,
        # Stable uid so legend-hidden categories stay hidden across redraws
        uid=uid,
        marker={
            'size': 7,
            'symbol': symbol,
            'color': hex_to_rgba(color, 0.35 if is_pass else 0.45),
            'line': {'color': color, 'width': 1 if is_pass else 1.5},
        },
    )


def make_figure(data: dict, view=None, uirevision=None, selectionrevision=None):
    """Build the figure for the current view. Returns (figure, status)."""
    keep, status = _choose_pass_points(data, view)

    hover = f'{data["x_label"]}: %{{x}}<br>{data["y_label"]}: %{{y}}'
    hover_flagged = hover + '<br>Failures: %{text}'

    color_map = _color_map()
    symbol_map = {MULTIPLE_TESTS: 'diamond', MANUALLY_FLAGGED: 'square'}

    traces = []

    if len(data['pass_x']):
        traces.append(
            _scatter(
                name=f'{m.PASS} (subset)' if status['sampled'] else str(m.PASS),
                uid=str(m.PASS),
                x=data['pass_x'][keep],
                y=data['pass_y'][keep],
                idx=data['pass_idx'][keep],
                text=None,
                hovertemplate=hover,
                color=color_map[m.PASS],
                is_pass=True,
                symbol='circle',
            )
        )

    for f in data['flagged']:
        traces.append(
            _scatter(
                name=f['name'],
                uid=f['name'],
                x=f['x'],
                y=f['y'],
                idx=f['idx'],
                text=f['text'],
                hovertemplate=hover_flagged,
                color=color_map.get(f['name'], '#6c757d'),
                is_pass=False,
                symbol=symbol_map.get(f['name'], 'circle'),
            )
        )

    xaxis = {'title': {'text': data['x_label']}, 'showgrid': True, 'zeroline': False}
    if data['x_is_date']:
        xaxis['type'] = 'date'

    fig = go.Figure(data=traces)
    fig.update_layout(
        template='plotly_white',
        dragmode='pan',
        hovermode='closest',
        showlegend=True,
        margin={'l': 60, 'r': 20, 't': 20, 'b': 55},
        legend={'title': {'text': 'Point status'}, 'y': 0.93, 'yanchor': 'top'},
        xaxis=xaxis,
        yaxis={'title': {'text': data['y_label']}, 'showgrid': True, 'zeroline': False},
        # Same uirevision -> browser keeps zoom/pan/dragmode/legend state across redraws.
        uirevision=uirevision,
        # New selectionrevision each build -> stale selections are cleared.
        selectionrevision=selectionrevision,
    )

    return fig, status


def describe_status(status):
    """(level, text) for the line above the plot, or None when nothing needs saying."""
    if not status or not status['large']:
        return None

    if not status['sampled']:
        return 'success', 'Showing every point in this view.'

    return 'warning', (
        f'Showing a sample of passing points ({status["shown"]:,} of {status["in_view"]:,} in view). '
        'Flagged points are always shown. Zoom in to see all.'
    )
