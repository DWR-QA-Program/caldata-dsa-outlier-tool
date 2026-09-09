# Functions and objects related to setting up a UI for outlier detection tests.
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from shiny import Inputs, reactive, ui

from . import od, od_core
from .app_ui import trash_svg

from .caching import (
    clear_station_test_defaults,
    get_station_test_defaults,
    set_station_test_defaults,
)

@dataclass
class ODTest:
    """Represents an outlier detection test"""

    test_key: str  # name of test as defined in od.OD_IMPLEMENTED
    test_col: str  # column the test reads: the analyte's values, or the date column
    analyte: str = ''  # analyte this test was selected for
    date_col: str = '' # date of sampling event
    _fn_kwargs: dict[str, Any] | None = field(default_factory=dict)
    _user_input_locations: list[tuple[str, str]] | None = field(default_factory=list)

    # This is needed to support adding this object to a set.
    def __hash__(self):
        return hash((self.test_key, self.test_col, self.analyte))

    # This is needed to support adding this object to a set.
    def __eq__(self, other):
        return all(
            [
                self.test_key == other.test_key,
                self.test_col == other.test_col,
                self.analyte == other.analyte,
            ]
        )

    def get_argument(self, arg_id, default_value=None):
        return self._fn_kwargs.get(arg_id, default_value)

    def save_argument_info(self, arg_id, input_id):
        self._user_input_locations.append((arg_id, input_id))

    # Brings test argument values from client into server
    def gather_user_arguments(self, input_obj: Inputs):
        for arg_id, input_id in self._user_input_locations:
            self._fn_kwargs[arg_id] = getattr(input_obj, input_id)()

    # The analyte selects which rows the test runs on (all of them, in wide
    # format); test_col selects which column within those rows. run_od resolves
    # both into a series and keys the result store on (analyte, test_key).
    def to_test_arguments(self):
        return (
            self.test_key,
            self.analyte,
            self.test_col,
            self._fn_kwargs,
        )


class ODTestSet:
    """Represents a set of unique outlier detection tests"""

    def __init__(self, tests=None):
        self.tests = tests if tests is not None else set()

    def __len__(self):
        return len(self.tests)

    def __iter__(self):
        yield from self.tests

    # Returns number of elements added to internal set
    def add(self, *args, **kwargs) -> int:
        obj = ODTest(*args, **kwargs)
        if obj not in self.tests:  # don't overwrite existing one to preserve state
            self.tests.add(obj)
            return 1
        return 0

    def remove(self, test):
        self.tests.remove(test)

    def copy(self):  # shallow copy
        return ODTestSet(tests=self.tests)

    def gather_user_arguments(self, input_obj: Inputs):
        for test in self:
            test.gather_user_arguments(input_obj)

    def remove_by_hash(self, hash_value: int):
        for test in self:
            if hash(test) == hash_value:
                self.remove(test)
                return
        raise ValueError(f'value {hash_value} not found')

    # This function enables the server to show the user a list of accordions, one
    # per test, grouped under a header per analyte. The user will be able to edit
    # test parameters/arguments and those values will be collected when "run tests"
    # is clicked.
    def get_ui(self, input_obj: Inputs, station_id: str | None = None):
        panels_by_analyte = {}

        with reactive.isolate():
            self.gather_user_arguments(input_obj)

        def build_arg_inputs(test, method_key, base_id):
            method_info = od.OD_IMPLEMENTED[method_key]
            inputs = []

            for (
                arg_id,
                arg_label,
                arg_type,
                default_value,
                *rest,
            ) in method_info.get('args', ()):
                arg_help = rest[0] if rest else None
                input_id = f'{base_id}_{method_key}_{arg_id}'
                existing_value = test.get_argument(arg_id, default_value)

                if arg_type is str:
                    arg_input = ui.input_text(
                        input_id,
                        f'{arg_label}:',
                        existing_value,
                    )
                elif arg_type in (int, float):
                    arg_input = ui.input_numeric(
                        input_id,
                        f'{arg_label}:',
                        existing_value,
                    )
                elif arg_type == 'date_unit':
                    arg_input = ui.input_select(
                        input_id,
                        arg_label,
                        od_core.DATE_STRS,
                        selected=existing_value,
                    )
                else:
                    arg_input = None

                if arg_input is None:
                    continue

                inputs.append(
                    ui.div(
                        arg_input,
                        ui.p(
                            arg_help,
                            class_='text-muted small mb-0',
                        ) if arg_help else None,
                    )
                )

                test.save_argument_info(arg_id, input_id)

            return inputs

        # helper
        def test_setup_status(test):
            test_info = od.OD_TESTS[test.test_key]
            methods = test_info['methods']
            method_mode = test_info['method_mode']

            if method_mode == 'choose_one':
                return 'review settings', 'text-danger'

            has_args = any(
                od.OD_IMPLEMENTED[method_key].get('args')
                for method_key in methods
            )

            if has_args:
                return 'review settings', 'text-danger'

            return 'no setup needed', 'text-success'

        for test in sorted(self, key=lambda t: (t.analyte, t.test_key)):
            test._user_input_locations.clear()

            test_info = od.OD_TESTS[test.test_key]
            methods = test_info['methods']
            method_mode = test_info['method_mode']

            if station_id:
                cached = get_station_test_defaults(
                    station_id,
                    test.test_key,
                    test.analyte,
                )
                if cached:
                    for key, value in cached.items():
                        test._fn_kwargs.setdefault(key, value)

            base_id = (
                f'{test.test_key}_{test.test_col.replace(" ", "_")}'
                f'_{test.analyte.replace(" ", "_")}'
            )

            body = []

            if method_mode == 'choose_one':
                method_id = f'{base_id}_method'
                selected_method = test.get_argument('_method', methods[0])

                if selected_method not in methods:
                    selected_method = methods[0]

                body.append(
                    ui.div(
                        ui.strong('Method:'),
                        ui.div(
                            ui.input_radio_buttons(
                                method_id,
                                None,
                                test_info['method_choices'],
                                selected=selected_method,
                                inline=True,
                            ),
                            class_='method-radio',
                        ),
                        style=(
                            'display: flex; '
                            'align-items: baseline; '
                            'gap: 10px; '
                            'margin-bottom: 0.5rem;'
                        ),
                    )
                )

                test.save_argument_info('_method', method_id)

                for method_key in methods:
                    method_info = od.OD_IMPLEMENTED[method_key]
                    method_body = []

                    if help_text := method_info.get('help'):
                        method_body.append(
                            ui.p(
                                help_text,
                                class_='text-muted small',
                            )
                        )

                    method_inputs = build_arg_inputs(
                        test,
                        method_key,
                        base_id,
                    )

                    if method_inputs:
                        method_body.append(
                            ui.layout_columns(
                                *method_inputs,
                                col_widths=method_info.get('col_widths'),
                            )
                        )
                    else:
                        method_body.append(
                            ui.p(
                                'No additional settings needed.',
                                class_='text-muted small',
                            )
                        )

                    body.append(
                        ui.panel_conditional(
                            f'input["{method_id}"] === "{method_key}"',
                            *method_body,
                        )
                    )

            elif method_mode == 'all':
                body.append(
                    ui.p(
                        ui.strong('Method:'),
                        f' {test_info["method_label"]}',
                        class_='mb-2',
                    )
                )

                if help_text := test_info.get('help'):
                    body.append(
                        ui.p(
                            help_text,
                            class_='text-muted small',
                        )
                    )

                for method_key in methods:
                    method_info = od.OD_IMPLEMENTED[method_key]
                    method_inputs = build_arg_inputs(
                        test,
                        method_key,
                        base_id,
                    )

                    if method_inputs:
                        body.append(
                            ui.layout_columns(
                                *method_inputs,
                                col_widths=method_info.get('col_widths'),
                            )
                        )

            else:
                method_key = methods[0]
                method_info = od.OD_IMPLEMENTED[method_key]

                body.append(
                    ui.p(
                        ui.strong('Method:'),
                        f' {method_info["plain"]}',
                        class_='mb-2',
                    )
                )

                if help_text := method_info.get('help'):
                    body.append(
                        ui.p(
                            help_text,
                            class_='text-muted small',
                        )
                    )

                method_inputs = build_arg_inputs(
                    test,
                    method_key,
                    base_id,
                )

                if method_inputs:
                    body.append(
                        ui.layout_columns(
                            *method_inputs,
                            col_widths=method_info.get('col_widths'),
                        )
                    )

            value = str(hash(test))
            analyte = test.analyte or test.test_col

            status_text, status_class = test_setup_status(test)

            title = ui.div(
                ui.span(
                    test_info['label'],
                    # class_='fw-semibold',
                ),
                ui.span(' ('),
                ui.span(
                    status_text,
                    class_=status_class,
                ),
                ui.span(')'),
            )

            panels_by_analyte.setdefault(analyte, []).append(
                ui.accordion_panel(
                    title,
                    *body,
                    icon=ui.tags.span(
                        ui.HTML(trash_svg),
                        class_='clickable-accordion-trash-icon',
                        data_panel_value=value,
                    ),
                    value=value,
                )
            )

        sections = []

        for i, (analyte, panels) in enumerate(panels_by_analyte.items()):
            sections.append(
                ui.tags.h6(
                    analyte,
                    class_='fw-semibold mb-1' if i == 0 else 'fw-semibold mt-3 mb-1',
                )
            )
            sections.append(
                ui.accordion(
                    *panels,
                    open=False,
                )
            )

        return ui.div(*sections)

    # Format tests into runnable list of tests
    def get_test_list(self, input_obj: Inputs) -> list[tuple[str, str, str, dict]]:
        self.gather_user_arguments(input_obj)
        test_list = []

        def get_method_args(method_key, values):
            allowed_args = {
                arg[0]
                for arg in od.OD_IMPLEMENTED[method_key].get('args', ())
            }

            return {
                key: value
                for key, value in values.items()
                if key in allowed_args
            }

        for test in self:
            test_info = od.OD_TESTS[test.test_key]
            methods = test_info['methods']
            values = dict(test._fn_kwargs or {})

            if test_info['method_mode'] == 'choose_one':
                methods = (
                    values.get('_method', methods[0]),
                )

            for method_key in methods:
                method_info = od.OD_IMPLEMENTED[method_key]

                test_col = (
                    test.date_col
                    if method_info['ts_col_type'] == 'x'
                    else test.test_col
                )

                test_list.append(
                    (
                        method_key,
                        test.analyte,
                        test_col,
                        get_method_args(method_key, values),
                    )
                )

        return test_list

    # Presist test values for a given station
    def persist_station_defaults(self, station_id: str, input_obj: Inputs) -> None:
        """
        Persist current argument values for all tests with given Station_ID key

        Behavior:
        - Captures latest browser values into each ODTest._fn_kwargs
        - If a test has no args, does nothing for that test
        - If all arg values are None (or none exist), clears the stored defaults
        - Otherwise stores the full arg dict for that station/analyte/test
        """

        if not station_id:
            return

        # Capture latest values from the browser into each ODTest._fn_kwargs
        self.gather_user_arguments(input_obj)

        for test in self:
            test_info = od.OD_IMPLEMENTED.get(test.test_key, {})
            if 'args' not in test_info:
                continue

            # Store the whole argument dict; if everything is None, remove remembered defaults
            defaults = dict(test._fn_kwargs) if test._fn_kwargs else {}
            if (not defaults) or all(v is None for v in defaults.values()):
                clear_station_test_defaults(station_id, test.test_key, test.analyte)
            else:
                set_station_test_defaults(station_id, test.test_key, test.analyte, defaults)