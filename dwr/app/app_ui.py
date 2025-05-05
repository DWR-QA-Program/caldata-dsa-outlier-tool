from htmltools import tags
from shiny import ui

from shinywidgets import output_widget
import shinyswatch

import m
import od
import upload_util

app_ui = ui.page_sidebar(
            ui.sidebar(
                #ui.output_image('logo'),
                shinyswatch.theme_picker_ui(),
                open='closed',
            ),
            ui.navset_pill(
                ui.nav_panel('Import',
                    ui.row(
                        ui.column(3,
                            ui.input_checkbox_group(
                                'upload_settings',
                                'Preprocessing settings:',
                                {
                                    'data_has_header': upload_util.upload_checkbox(
                                        'File has header',
                                        'Uncheck if uploaded file has no header at the top row.'
                                    ),
                                    'upload_nullify_hyphens': upload_util.upload_checkbox(
                                        'Nullify hyphen-only cells',
                                        'Update any values consisting of only hyphens (-) to contain no value. Then, attempt to convert any affected columns to a numeric type.'
                                    ),
                                },
                                selected=[
                                    'data_has_header',
                                    'upload_nullify_hyphens',
                                ]
                            ),
                            ui.input_file('file1', 'Choose CSV File:', accept=['.csv',], multiple=False),
                        ),
                        ui.column(4,
                            ui.output_ui('upload_text'),
                        ),
                        ui.column(5,
                            ui.output_ui('show_upload_od_feedback'),
                        ),
                    ),
                ),
                ui.nav_panel('Explore',
                    ui.row(
                        ui.input_select('sel_files_table', 'File:', []),
                        ui.input_checkbox('checkbox_show_od_cols', 'Show Outlier Detection Columns', False),
                    ),
                    ui.output_data_frame('explore_table'),
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
                            ui.hr(),
                            ui.row(
                                ui.input_selectize(
                                    'sel_od_functions',
                                    'Outlier Detection:',
                                    choices=list(od.OD_IMPLEMENTED.keys()),
                                    multiple=True,
                                ),
                                ui.column(1,
                                    ui.input_action_button('btn_od', 'Go', class_='btn-primary', style='height:90%;')
                                ),
                            ),
                            ui.output_ui('od_function_inputs'),
                        ),
                        ui.column(7,
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
                    ui.br(),
                ),
                ui.nav_panel('Export',
                    ui.input_select('sel_files_export', 'Choose file to export:', []),
                    ui.input_checkbox_group(
                        'export_settings',
                        '',
                        {
                            'include_header': upload_util.upload_checkbox(
                                'Include header',
                                'Exported file will include header row when checked',
                            ),
                        },
                        selected=[
                            'include_header',
                        ],
                    ),
                    ui.input_select('sel_export_format', 'File format:', ['.csv', '.xlsx']),
                    ui.input_text('text_export_custom_fname', 'Custom file name (optional):', ''),
                    ui.div(
                        tags.label('Download:', for_='download_data', class_='control-label'),
                        ui.div(
                            ui.output_ui('show_download_button'),
                        ),
                    ),
                ),
                ui.nav_panel('Experimental 🧪',
                    ui.input_select('sel_files_columns', 'File:', []), # FIXME: confusing name
                    ui.row(
                        ui.column(3,
                            ui.input_selectize('sel_ph_col', 'Label as pH:', choices=[], multiple=True),
                            ui.input_action_button('btn_ph_col_sel', 'Go', class_='btn-primary')
                        ),
                    style='flex-wrap: nowrap;'),
                ),
                ui.nav_spacer(),
                ui.nav_panel('Settings',
                    ui.br(),
                    ui.p('Under construction'),
                ),
                ui.nav_panel('Help',
                    ui.p('Placeholder'),
                ),
            ),
            ui.include_js('js/util.js'),
            ui.include_css('css/misc.css'),
    #title='Tool', # takes up too much space
    window_title=m.WINDOW_TITLE,
    theme=m.DEFAULT_THEME,
)
