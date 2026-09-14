"""User-facing text for the DWR Outlier Tool UI.

Plain strings only — no shiny imports — so this module stays trivially
importable and diff-friendly for copy review. Anything needing markup gets
assembled at the call site in app_ui.py.

Short widget labels ('Analyte:', 'File:') deliberately stay inline in
app_ui.py; moving them here costs more in readability than it buys.
"""

# home tab ----------------------------------------------------------------

HOME_TITLE = 'DWR Outlier Tool'
HOME_INTRO = (
    'Identifies and flags outliers for a selected continuous water-quality '
    'parameter.'
)
HOME_BULLETS = (
    'Dates are displayed on the x-axis.',
    'Numeric values are displayed on the y-axis.',
)
HOME_CONTACT = 'Questions: Contact DWR QA Section'

GUIDANCE_TITLE = 'Guidance'
GUIDANCE_BODY = 'Some basic guidance on tool use?'  # TODO: real copy


# upload tab --------------------------------------------------------------

UPLOAD_CARD_TITLE = 'Upload data'
FILE_FORMAT_CARD_TITLE = 'About file formats'
FILE_FORMAT_BLURB = (
    'Choose a predefined format only when your file follows one of the listed '
    'formats. This tells the tool how to parse the data. Otherwise, leave the '
    'selection as None.'
)

# (label, help text) pairs -> upload_util.checkbox_with_help(*PAIR)
CHK_HAS_HEADER = (
    'Count first row as header',
    'Uncheck if uploaded file has no header at the top row.',
)
CHK_SKIP_ROWS = (
    'Ignore rows',
    'The number of rows specified will be ignored.',
)
CHK_DATA_IS_LONG = (
    'Data is in long format',
    'Check if each row is a single measurement, with analyte names in one '
    'column and results in another.',
)


# check tab ---------------------------------------------------------------

CHECK_TITLE = 'Check columns and preview data'
COLOR_KEY_LABEL = 'Column color key:'


# test tab ----------------------------------------------------------------

TEST_TITLE = 'Set up and run outlier tests'
TEST_AVAILABLE_BLURB = 'Choose a primary analyte and one or more tests.'
TEST_SELECTED_BLURB = 'Some tests may need additional input.'

# Group metadata. Keys are the group ids used in _test_setup_left.
TEST_GROUP_INFO = {
    'value': (
        'Value-Based Tests',
        'These tests evaluate individual values.',
    ),
    'sequential': (
        'Time-Based Tests',
        'These tests evaluate patterns over time.',
    ),
    'comparison': (
        'Comparison tests',
        'These tests evaluate outliers in relation to another analyte.',
    ),
}

DEFAULT_TEST_GROUP = 'value'

# Warnings raised by _test_setup_left
WARN_NO_DATA = 'No data available to test.'
WARN_NO_ANALYTES = (
    'No analytes were found. Check that the correct analyte column was '
    'selected on the Upload tab.'
)
WARN_NO_NUMERIC_COLS = (
    'No columns are available to test. You may need to upload a file with '
    'more numeric columns.'
)


# review tab --------------------------------------------------------------

REVIEW_TITLE = 'Review and flag outliers'
REVIEW_STEP_1 = '1. Select outliers using'  # icon appended at call site
REVIEW_STEP_2 = '2. Click "toggle flag" to manually flag/unflag data'
REVIEW_TEST_SUMMARY = 'Test summary:'


# export tab --------------------------------------------------------------

EXPORT_TITLE = 'Export your data'
EXPORT_PREVIEW = 'Export preview:'

CHK_INCLUDE_HEADER = (
    'Include header',
    'Exported file will include header row when checked',
)
CHK_INCLUDE_PASSING = (
    'Include passing tests',
    'When checked, the exported file will also include outlier test results ',
    'that yielded no failures.',
)

