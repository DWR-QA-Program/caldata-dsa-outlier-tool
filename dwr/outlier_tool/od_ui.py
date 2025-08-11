# Functions and objects related to setting up a UI for outlier detection tests.
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from shiny import Inputs, reactive, ui

from . import od
from .app_ui import trash_svg


@dataclass
class ODTest:
    """Represents an outlier detection test"""

    test_key: str  # name of test as defined in od.OD_IMPLEMENTED
    test_col: str
    _fn_kwargs: dict[str, Any] | None = field(default_factory=dict)
    _user_input_locations: list[tuple[str, str]] | None = field(default_factory=list)

    # This is needed to support adding this object to a set.
    def __hash__(self):
        return hash((self.test_key, self.test_col))

    # This is needed to support adding this object to a set.
    def __eq__(self, other):
        return all(
            [
                self.test_key == other.test_key,
                self.test_col == other.test_col,
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

    def to_test_arguments(self):
        return (
            od.OD_IMPLEMENTED[self.test_key]['fn'],
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
    # per test. The user will be able to edit test parameters/arguments and those
    # values will be collected when "run tests" is clicked.
    def get_ui(self, input_obj: Inputs):
        accordions = []

        # Every time this function is called, all accordions are replaced. As a convenience
        # to the user, we manually populate arguments they already inputted previously.
        # In order to do that, we have to save the latest arguments.
        with reactive.isolate():  # don't trigger this on each argument edit
            self.gather_user_arguments(input_obj)

        # Create one accordion per test
        for test in self:
            # Create one input object per test argument
            inputs = []
            if 'args' not in od.OD_IMPLEMENTED[test.test_key]:
                inputs.append(ui.p('No additional arguments needed.'))
            else:
                for arg_id, arg_label, arg_type, default_value in od.OD_IMPLEMENTED[test.test_key]['args']:
                    # Create unique identifier of this argument so we can search for it later
                    input_id = f'{test.test_key}_{test.test_col.replace(" ", "_")}_{arg_id}'
                    existing_value = test.get_argument(arg_id, default_value)  # can return None
                    print(arg_id, existing_value)

                    if arg_type is str:
                        inputs.append(ui.input_text(input_id, f'{arg_label}:', existing_value))
                    elif arg_type in (int, float):
                        inputs.append(ui.input_numeric(input_id, f'{arg_label}:', existing_value))
                    elif arg_type == 'date_unit':
                        inputs.append(
                            ui.input_select(input_id, arg_label, od.DATE_STRS, selected=existing_value)
                        )

                    # Save information needed to correlate an argument in the browser
                    # with a test object.
                    test.save_argument_info(arg_id, input_id)

            # This uniquely identifies an internal test object so we'll use it to
            # also uniquely identify accordion panels.
            value = str(hash(test))

            plain_name = od.OD_IMPLEMENTED[test.test_key]['plain']
            col_widths = od.OD_IMPLEMENTED[test.test_key].get('col_widths', None)
            title = f'{plain_name}: {test.test_col}'

            accordions.append(
                ui.accordion_panel(
                    title,
                    ui.layout_columns(*inputs, col_widths=col_widths),
                    icon=ui.tags.span(
                        ui.HTML(trash_svg),
                        class_='clickable-accordion-trash-icon',
                        data_panel_value=value,  # this becomes data-panel-value in the browser
                    ),
                    value=value,
                )
            )
        return ui.accordion(*accordions, open=False)

    # Format tests into runnable list of tests
    def get_test_list(self, input_obj: Inputs) -> list[tuple[Callable, str, dict]]:
        self.gather_user_arguments(input_obj)
        return [test.to_test_arguments() for test in self]
