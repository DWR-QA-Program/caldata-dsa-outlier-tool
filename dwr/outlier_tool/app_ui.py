import shinyswatch
from htmltools import tags
from shiny import ui
from shinywidgets import output_widget

from . import m, schema, upload_util, util, text


# Returns names (ids) of file selectors managed by the UI.
def get_file_selector_names():
    return [
        'sel_files_check',
        'sel_files_test',
        'sel_files_viz',
        'sel_files_export',
    ]


# Load our icons into memory so we can put them inline later.
def load_icon(path, default=''):
    try:
        with open(path) as f:
            svg = f.read()
    except Exception as e:
        print(repr(e))
        svg = default
    return svg


box_svg = load_icon(m.DOTTED_BOX_ICON)
trash_svg = load_icon(m.TRASH_ICON, default='X')

# Column 2 of the Check tab. Both shapes answer "where are the analytes",
# just differently: wide names the columns, long names the column that holds
# the names plus the column that holds the values.
def _analyte_selects(
    cols: list[str],
    numeric_cols: list[str],
    is_long: bool,
):
    if is_long:
        return ui.TagList(
            ui.input_select(
                'sel_long_analyte_col',
                ui.span(
                    'Analyte Name column:',
                    class_='fw-semibold',
                ),
                cols,
                selected=upload_util.guess_col(
                    cols,
                    ('analyte', 'parameter', 'constituent', 'param'),
                ),
            ),
            ui.input_select(
                'sel_long_value_col',
                ui.span(
                    'Analyte Value column:',
                    class_='fw-semibold',
                ),
                cols,
                selected=upload_util.guess_col(
                    cols,
                    ('value', 'result', 'concentration', 'conc', 'reading'),
                ),
            ),
        )

    return ui.input_selectize(
        'sel_wide_analyte_cols',
        ui.span(
            'Analyte column(s):',
            class_='fw-semibold',
        ),
        cols,
        selected=numeric_cols,
        multiple=True,
    )

def _data_shape_options():
    return ui.input_radio_buttons(
        'radio_data_shape',
        ui.div(
            'How are analyte values listed?',
            class_='fw-semibold',
            style='padding-bottom: 6px;',
        ),
        {
            'wide': 'Separate columns (wide format)',
            'long': 'One column (long format)',
        },
        selected=None,
    )

def show_upload_options():
    return ui.div(
        ui.input_checkbox(
            'checkbox_data_has_header',
            upload_util.checkbox_with_help(
                'Count first row as header', 'Uncheck if uploaded file has no header at the top row.'
            ),
            value=True,
        ),
        ui.input_checkbox(
            'checkbox_skip_n_rows',
            upload_util.checkbox_with_help('Ignore rows', 'The number of rows specified will be ignored.'),
        ),
        ui.output_ui('show_rows_to_skip'),
        id='upload_options',
        class_='mt-3',
    )


# `info` carries:
#   'tests'      -> dict of available tests
#   'x_columns'  -> candidate date columns
#   'y_columns'  -> candidate numeric columns (wide mode)
#   'is_long'    -> bool, True when the uploaded file is in long format
#   'analytes'   -> unique values from the analyte column (long mode)
def _test_setup_left(info: dict[str, list | dict]):
    if not info:
        return ui.panel_well(util.warning(text.WARN_NO_DATA))

    is_long = info.get('is_long', False)

    if is_long:
        analyte_choices = info.get('analytes') or []
        if not analyte_choices:
            return ui.panel_well(util.warning(text.WARN_NO_ANALYTES))
    else:
        analyte_choices = info['y_columns']
        if not analyte_choices:
            return ui.panel_well(util.warning(text.WARN_NO_NUMERIC_COLS))

    test_groups = {group: {} for group in text.TEST_GROUP_INFO}

    for test_key, test_info in info['tests'].items():
        group = test_info.get('group', text.DEFAULT_TEST_GROUP)
        label = test_info['label']
        desc = test_info.get('desc')
        if desc:
            label = upload_util.checkbox_with_help(label, desc)
        test_groups[group][test_key] = label

    def test_section(
        title: str,
        description: str,
        input_id: str,
        choices: dict,
    ):
        return ui.div(
            ui.div(
                title,
                class_='fw-semibold mb-1',
            ),
            ui.p(
                description,
                class_='text-muted small mb-2',
            ),
            ui.div(
                style='height: 8px;',
            ),
            ui.input_checkbox_group(
                input_id,
                '',
                choices,
            ),
            class_='mb-4',
        )

    return ui.div(
        ui.div(
            'Choose tests',
            class_='h5 border-bottom pb-2 mb-3',
        ),

        ui.div(
            'Select Analyte(s):',
            class_='fw-semibold mb-1',
        ),
        ui.input_selectize(
            'sel_test_analyte',
            None,
            analyte_choices,
            selected=analyte_choices,
            multiple=True,
        ),

        *[
            test_section(
                title,
                description,
                f'chk_tests_{group}',
                test_groups[group],
            )
            for group, (title, description) in text.TEST_GROUP_INFO.items()
            if group != 'comparison'
        ],
    )

app_ui = ui.page_sidebar(
    ui.sidebar(
        shinyswatch.theme_picker_ui(),
        id='theme_sidebar',
        open='closed',
        title='Appearance',
    ),
    ui.head_content(tags.link(rel='icon', href=m.FAVICON_URL, type='image/x-icon')),
    ui.navset_pill(
        ui.nav_panel(
            'Home',
            ui.br(),
            tags.h4('DWR Outlier Tool', class_='tab-title'),
            tags.p(
                'Identifies and flags outliers for a selected '
                'continuous water-quality parameter.'
            ),
            tags.ul(
                tags.li('Dates are displayed on the x-axis.'),
                tags.li('Numeric values are displayed on the y-axis.')
            ),
            tags.p('Questions: Contact DWR QA Section'),
            tags.hr(),
            tags.h4('Guidance', class_='tab-title'),
            tags.p(
                'Some basic guidance on tool use?'
            ),
            tags.hr(),
            tags.p(
                tags.strong('Version:'),
                ' 0.1.1',
                class_='text-muted'
            ),
        ),
        ui.nav_panel(
            '1. Upload',
            ui.br(),
            ui.card(
                ui.card_header('Upload Data', class_='h5 mb-0'),
                ui.layout_sidebar(
                    ui.sidebar(
                        ui.input_select(
                            'sel_file_format',
                            ui.span(
                                'File format (optional): ',
                                ui.tooltip(
                                    ui.span('\u2139'),
                                    'Choose a predefined format only when your file follows one of '
                                    'the listed formats. This tells the tool how to parse the data. '
                                    'Otherwise, leave the selection as None.',
                                ),
                            ),
                            [m.NO_FF, *schema.get_all_schema_names()],
                        ),
                        ui.input_file(
                            'file1',
                            'File:',
                            multiple=False,
                        ),
                        ui.output_ui('upload_options'),
                        width=350,
                        open='always',
                    ),
                    ui.output_ui('upload_text'),
                ),
                fill=False,
                class_='mb-3',
            ),
        ),
        ui.nav_panel(
            '2. Define format',
            ui.br(),

            ui.div(
                ui.input_select(
                    'sel_files_check',
                    'File:',
                    [],
                ),
                style='display: none;',
            ),

            ui.card(
                ui.card_header(
                    'Define Data Format',
                    class_='h5 mb-0',
                ),

                ui.layout_sidebar(
                    ui.sidebar(
                        ui.output_ui('data_shape_options'),
                        ui.output_ui('analyte_selects'),

                        ui.input_select(
                            'sel_check_date',
                            ui.span(
                                'Date column:',
                                class_='fw-semibold',
                            ),
                            [],
                        ),

                        ui.input_select(
                            'sel_station_col',
                            ui.span(
                                'Station column (optional):',
                                class_='fw-semibold',
                            ),
                            {'': '(none)'},
                            selected='',
                        ),

                        ui.output_ui('station_col_warning'),

                        ui.input_action_button(
                            'btn_confirm_format',
                            'Confirm format',
                            class_='btn-primary',
                            style='width: 100%;',
                        ),

                        width=380,
                        open='always',
                    ),

                    ui.output_ui('format_preview'),
                ),

                fill=False,
                class_='mb-3',
            ),
        ),
        ui.nav_panel(
            '3. Test data',
            ui.br(),

            ui.row(
                ui.input_select(
                    'sel_files_test',
                    'File:',
                    [],
                ),
                style='display: none;',
            ),

            # Choose and configure tests
            ui.card(
                ui.card_header(
                    'Test Setup',
                    class_='h5 mb-0',
                ),
                ui.layout_sidebar(
                    ui.sidebar(
                        ui.output_ui('test_setup_left'),
                        ui.input_action_button(
                            'btn_test_move',
                            'Add selected tests \u2192',
                            class_='btn-primary',
                            style='width: 100%;',
                        ),
                        width=380,
                        open='always',
                    ),
                    ui.output_ui('test_setup_right'),
                ),
                fill=False,
                class_='mb-3',
            ),

            # Run tests
            ui.div(
                ui.input_action_button(
                    'btn_od',
                    'Run selected tests',
                    class_='btn-primary',
                ),
                style=(
                    'display: flex; '
                    'justify-content: center; '
                    'margin: 1rem 0;'
                ),
            ),

            # Run tests and show results
            ui.card(
                ui.card_header(
                    'Test Results',
                    class_='h5 mb-0',
                ),
                ui.output_ui('od_results_summary'),
                fill=False,
            ),
        ),
    ui.nav_panel(
        '4. Review outliers',
        ui.br(),

        ui.div(
            ui.input_select(
                'sel_files_viz',
                'File:',
                [],
            ),
            style='display: none;',
        ),

        ui.card(
            ui.card_header(
                'Review Outliers',
                class_='h5 mb-0',
            ),

            ui.layout_sidebar(
                ui.sidebar(
                    ui.div(
                        ui.div(
                            'Instructions:',
                            class_='fw-semibold',
                            style='margin-bottom: 3px;',
                        ),
                        ui.tags.ol(
                            ui.tags.li(
                                'Select outliers using ',
                                ui.HTML(box_svg),
                                ' in the upper-right corner of the graph',
                            ),
                            ui.tags.li(
                                'Click "Toggle Flag" to manually flag data',
                            ),
                            style='padding-left: 1.5rem; margin-bottom: 2px;',
                        ),

                        ui.tags.em(
                            'Tip: Click a legend item to hide those points',
                            class_='text-muted',
                        ),
                    ),

                    ui.hr(
                        style='margin: 10px 0 8px 0;',
                    ),

                    ui.input_select(
                        'sel_review_analyte',
                        ui.span(
                            'Analyte to review:',
                            class_='fw-semibold',
                        ),
                        [],
                    ),

                    ui.div(
                        'Test results',
                        class_='fw-semibold mb-1',
                    ),

                    ui.output_ui('review_test_summary'),

                    ui.hr(
                        style='margin: 10px 0 8px 0;',
                    ),

                    ui.input_select(
                        'sel_review_against',
                        ui.span(
                            'Plot against:',
                            class_='fw-semibold',
                        ),
                        {},
                    ),

                    width=380,
                    open='always',
                ),

                ui.div(
                    ui.output_ui('review_plot_title'),

                    ui.output_ui('review_match_message'),

                    ui.div(
                        output_widget('plot_data'),
                        style=(
                            'border: 1px solid #dee2e6; '
                            'border-radius: 6px; '
                            'padding: 6px; '
                            'background: #fff;'
                        ),
                    ),

                    ui.div(
                        ui.input_action_button(
                            'btn_undo_flag',
                            'Undo',
                            class_='btn-light',
                        ),
                        ui.input_action_button(
                            'btn_toggle_flag',
                            'Toggle Flag',
                            class_='btn-secondary',
                        ),
                        ui.input_action_button(
                            'btn_redo_flag',
                            'Redo',
                            class_='btn-light',
                        ),
                        style=(
                            'display: flex; '
                            'justify-content: center; '
                            'gap: 6px; '
                            'margin-top: 1rem;'
                        ),
                    ),

                    class_='p-2',
                ),
            ),

            fill=False,
            class_='mb-3',
        ),
    ),
    ui.nav_panel(
        '5. Export',
        ui.br(),

        ui.div(
            ui.input_select(
                'sel_files_export',
                'File:',
                [],
            ),
            style='display: none;',
        ),

        ui.card(
            ui.card_header(
                'Export Data',
                class_='h5 mb-0',
            ),

            ui.layout_sidebar(
                ui.sidebar(
                    ui.div(
                        'Export Settings',
                        class_='h5 border-bottom pb-2 mb-1',
                    ),
                    ui.input_select(
                        'sel_export_format',
                        'File format:',
                        ['.csv', '.xlsx'],
                    ),

                    ui.input_text(
                        'text_export_custom_fname',
                        'Custom file name (optional):',
                        '',
                    ),

                    ui.input_checkbox_group(
                        'export_settings',
                        '',
                        {
                            'include_header': 'Include header',
                        },
                        selected=['include_header'],
                    ),

                    ui.hr(style='margin: 12px 0;'),

                    ui.output_ui('show_download_button'),
                    ui.output_ui('export_filename'),

                    width=380,
                    open='always',
                ),

                ui.div(
                    ui.div(
                        'Export Preview',
                        class_='h5 border-bottom pb-2 mb-3',
                    ),
                    ui.output_data_frame('export_table'),
                    style='margin-top: -4px;',
                ),
            ),

            fill=False,
            class_='mb-3',
        ),
    ),

    id='navigation_bar',
),

ui.include_js(m.JS_UTIL),
ui.include_css(m.CSS_MISC),
window_title=m.WINDOW_TITLE,
theme=m.DEFAULT_THEME,
)
