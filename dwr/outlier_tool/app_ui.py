from htmltools import tags
from shiny import ui

from shinywidgets import output_widget
import shinyswatch

from . import m
from . import od
from . import util
from . import upload_util

# Load our icons into memory so we can put them inline later. It would be more
# natural to serve them as an image but shiny doesn't seem to support simple file
# serving, and we don't really want to have to call a render.image function, so
# we do things manually.
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


def _test_setup_left(info: dict[str, list|dict]):
    if not info or not info['y_columns']:                                                                      return ui.panel_well(                                                                                      util.warning('No columns are available to test. You may need to upload a file with more numeric columns.'))

    # Set up element 1: checkbox list of date columns
    x_columns = info['x_columns']
    x_boxes = ui.input_checkbox_group(
        'x_boxes',
        '',
        x_columns,
    )

    # Set up element 2: checkbox list of numeric columns
    y_boxes = ui.input_checkbox_group(
        'y_boxes',
        '',
        info['y_columns'],
    )

    # Set up element 3: checkbox list of tests
    test_checkbox_dict = {}
    for test_key, test_info in info['tests'].items():
        plain_name = test_info['plain']
        ts_col_type = test_info['ts_col_type']

        if ts_col_type == 'x':
            extra_text = ' (dates only)'
        elif ts_col_type == 'y':
            extra_text = ' (numeric only)'
        else:
            extra_text = ''
        test_checkbox_dict[test_key] = f'{plain_name}{extra_text}'

    test_boxes = ui.input_checkbox_group(
        'test_boxes',
        '',
        test_checkbox_dict,
    )

    return ui.panel_well(                                                                                      ui.row(
            ui.column(6,
                ui.p('Date column(s):'),
                x_boxes,
                ui.p('Numeric column(s):'),
                y_boxes,
            ),
            ui.column(6,
                ui.p(
                    'Test(s):',
                    ui.tooltip(
                        ui.span('\u2139', id='test_tooltip'),
                        'See "Help" page for test descriptions',
                    ),
                ),
                test_boxes
            ),
        ),
    )

def test_help_modal():
    return ui.modal(
        ui.p('Set up and run tests on your data in these steps:'),
        tags.ol(
            tags.li('Select tests'),
            tags.ul(
                tags.li('Check boxes to select column/test combinations, then click ">" to add to a test plan.'),
                tags.li('Incompatible column/test pairs will be ignored.'),
            ),
            tags.li('Configure arguments'),
            tags.ul(
                tags.li('Some tests require additional inputs. Expand the accordions to modify these.'),
            ),
            tags.li('Run tests'),
            tags.ul(
                tags.li('Click "run tests" at the bottom of the page.'),
                tags.li('Tests can be re-run with new arguments.'),
            ),
            tags.li('View results'),
            tags.ul(
                tags.li('Results appear below and on the next page.'),
            ),
        ),
        title='Test setup help',
        easy_close=True,
        size='l'
    )

app_ui = ui.page_sidebar(
            ui.sidebar(
                #ui.output_image('logo'),
                shinyswatch.theme_picker_ui(),
                open='closed',
            ),
            ui.navset_pill(
                ui.nav_panel('1. Import',
                    ui.row(
                        tags.h4('DWR outlier tool', class_='tab-title'),
                    ),
                    ui.row(
                        ui.column(4,
                            ui.panel_well(
                                ui.input_file('file1', 'Import a file:', accept=['.csv', '.prn'], multiple=False),
                                ui.input_checkbox_group(
                                    'upload_settings',
                                    'Actions on this file:',
                                    {
                                        'data_has_header': upload_util.checkbox_with_help(
                                            'Count first row as header',
                                            'Uncheck if uploaded file has no header at the top row.'
                                        ),
                                        'upload_nullify_hyphens': upload_util.checkbox_with_help(
                                            'Treat hyphens as nulls',
                                            'Update any values consisting of only hyphens (-) to contain no value. Then, attempt to convert any affected columns to a numeric type.'
                                        ),
                                    },
                                    selected=[
                                        'data_has_header',
                                        'upload_nullify_hyphens',
                                    ]
                                ),
                            id='upload_well'),
                        ),
                        ui.column(4,
                            ui.panel_well(
                                tags.h5('About this tool'),
                                tags.ul(
                                    tags.li('Analyzes dates (x-axis) and numeric values (y-axis)'),
                                    tags.li('Allows you to identify and flag outliers in your data.'),
                                ),
                            ),
                        ),
                    ),
                    ui.br(),
                    ui.row(
                        ui.column(8,
                            ui.output_ui('upload_text'),
                        ),
                    ),
                ),
                ui.nav_panel('2. Check',
                    tags.h4('Ensure the data looks right', class_='tab-title'),
                    ui.input_select('sel_files_check', 'File:', []),
                    ui.output_data_frame('check_table'),
                ),
                ui.nav_panel('3. Test Data',
                    ui.row(
                        ui.column(6, 
                            tags.h4('Set up and run outlier tests', class_='tab-title'),
                        ),
                        ui.column(6, 
                            ui.input_action_button('btn_test_help', 'Test setup help', class_='btn-info'),
                        style='display: flex; justify-content: right; align-items: center;'),
                    ),
                    ui.row(
                        ui.input_select('sel_files_test', 'File:', []),
                    ),
                    ui.row(
                        ui.column(5,
                            ui.p('Select combinations of tests and columns and click ">":'),
                        ),
                        ui.column(1),
                        ui.column(6,
                            ui.span('Selected tests (some may need additional input):'),
                            #ui.input_radio_buttons(
                            #    'selected_tests_radio',
                            #    'Order by:',
                            #    {
                            #        'test_name': 'Test name',
                            #        'x_col': 'Date column',
                            #        'y_col': 'Numeric column',
                            #    },
                            #    inline=True
                            #),
                        ),
                    ),
                    ui.row(
                        ui.column(6,
                            ui.row(
                                ui.column(11,
                                    ui.output_ui('test_setup_left'),
                                ),
                                ui.column(1,
                                    ui.input_action_button('btn_test_move', '>', class_='btn-primary'),
                                style='display:flex; justify-content: center'),
                            ),
                        ),
                        ui.column(6,
                            ui.output_ui('test_setup_right'),
                        ),
                    ),
                    ui.br(),
                    ui.row(
                        ui.column(2,
                            ui.input_action_button('btn_od', 'Run tests', class_='btn-light', style='height:90%;'),
                        style='display:flex; justify-content: center'),
                    style='display:flex; justify-content: center'),
                    ui.row(
                        ui.column(8,
                            ui.output_data_frame('od_results_table'),
                        style='display:flex; justify-content: center'),
                    style='display:flex; justify-content: center'),
                ),
                ui.nav_panel('4. Review Outliers',
                    tags.h4('Review and flag outliers', class_='tab-title'),
                    ui.row(
                        ui.column(5,
                            ui.row(
                                ui.input_select('sel_files_viz', 'File:', []),
                            ),
                            ui.row(
                                ui.p('Test summary:'),
                                ui.output_data_frame('od_results_table_viz'),
                            ),
                        ),
                        ui.column(7,
                            ui.row(
                                ui.p(
                                    '1. Select outliers using',
                                    ui.HTML('&nbsp&nbsp'),
                                    ui.HTML(box_svg),
                                    ui.br(),
                                    '2. Click flag or unflag to change their status',
                                ),
                            ),
                            ui.row(
                                ui.input_select('sel_x', 'x-axis (date):', []),
                                ui.input_select('sel_y', 'y-axis (number):', []),
                            ),
                            ui.row(
                                ui.column(2),
                                ui.column(4,
                                    ui.input_action_button('btn_flag', 'Flag', class_='btn-danger', style='margin: 0 3px;'),
                                    ui.input_action_button('btn_unflag', 'Unflag', class_='btn-success', style='margin: 0 3px;'),
                                style='display:flex; justify-content: center'),
                                ui.column(4,
                                    ui.input_action_button('btn_undo_flag', 'Undo', class_='btn-light', style='margin: 0 3px;'),
                                    ui.input_action_button('btn_redo_flag', 'Redo', class_='btn-light', style='margin: 0 3px;'),
                                style='display:flex; justify-content: center'),
                                ui.column(2),
                            ),
                            ui.row(
                                output_widget('plot_data'),
                            ),
                        ),
                    ),
                ),
                ui.nav_panel('5. Export',
                    tags.h4('Export your data', class_='tab-title'),
                    ui.row(
                        ui.column(4,
                            ui.input_select('sel_files_export', 'Choose file to export:', []),
                            ui.input_checkbox_group(
                                'export_settings',
                                '',
                                {
                                    'include_header': upload_util.checkbox_with_help(
                                        'Include header',
                                        'Exported file will include header row when checked',
                                    ),
                                    'include_passing_cols': upload_util.checkbox_with_help(
                                        'Include passing tests',
                                        'When checked, the exported file will also include outlier test results that yielded no failures.',
                                    ),
                                },
                                selected=[
                                    'include_header',
                                ],
                            ),
                            ui.input_select('sel_export_format', 'File format:', ['.csv', '.xlsx']),
                        ),
                        ui.column(4, 
                            ui.input_text('text_export_custom_fname', 'Custom file name (optional):', ''),
                            ui.div(
                                tags.label('Download:', for_='download_data', class_='control-label'),
                                ui.div(
                                    ui.output_ui('show_download_button'),
                                ),
                            ),
                        ),
                    ),
                    ui.br(),
                    ui.row(
                        ui.p('Export preview:'),
                        ui.br(),
                        ui.output_data_frame('export_table'),
                    ),
                ),
                ui.nav_spacer(),
                ui.nav_panel('Help',
                    tags.h4('Help', class_='tab-title'),
                    ui.row(
                        ui.column(6,
                            ui.h5('Test descriptions'),
                            ui.accordion(
                                ui.accordion_panel(
                                    'Gross range test',
                                    ui.div(
                                        ui.p('The gross range test evaluates a column of numerical data against a minimum and/or maximum value. Values falling outside the minimum and maximum (not including the min/max themselves!) will be marked as failing.'),
                                    )
                                ),
                                ui.accordion_panel(
                                    'Time gap test',
                                    ui.div(
                                        ui.p('The time gap test evaluates a date column for gaps in its expected cadence. A cadence is a number of days, hours, or minutes.'),
                                    )
                                ),
                                ui.accordion_panel(
                                    'Value gap test',
                                    ui.div(
                                        ui.p('The value gap test simply tests for missing data in a column. This test requires no additional user input.'),
                                    )
                                ),
                                ui.accordion_panel(
                                    'Flat line test',
                                    ui.div(
                                        ui.p('The flat line test evaluates a column of data and marks repeated values as failing. The number of repetitions before failing can be configured. Failures apply to entire groups of repeated values, not just the first value that exceeds the repetition limit. Repeated missing values do not trigger failures.'),
                                    )
                                ),
                                open=False,
                            ),
                        ),
                    ),
                value='help_tab'),
            id='navigation_bar',
            ),
            ui.include_js(m.JS_UTIL),
            ui.include_css(m.CSS_MISC),
    window_title=m.WINDOW_TITLE,
    theme=m.DEFAULT_THEME,
)
