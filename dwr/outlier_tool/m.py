#
# 'm' stands for miscellaneous variables: it is kept short to promote code
# readability at the expense of mild confusion upon first seeing it.
#
import os
import shinyswatch

#
# File paths that enhance the tool's usability
#

# Directory of custom schema files
SCHEMA_DIR = 'outlier_tool/schemas'

# Paths of custom javascript/CSS files
JS_UTIL = 'outlier_tool/js/util.js'
CSS_MISC = 'outlier_tool/css/misc.css'

#
# Outlier detection column creation
#

# Used to create columns that denote manual flagging operations
MANUAL = 'manual_flag'
# Used to create column names for outlier detection tests
_F = '_failed_'


#
# Showing results of outlier detection
#

# Value (see graph legend) used to denote data that has not "failed" any outlier detection
PASS = 'Pass'

# Value (see graph legend) used to denote data that has "failed" multiple outlier detection tests
MULTIPLE_FAILURES = 'Failed multiple tests'

# Column name used by the app to denote a row's failed tests. Appears in tooltip.
FAILURES = 'Failed tests'

# Column name used by the app to denote a row's index
IDX = 'idx'

# Controls the graph's legend but also an internal column that gets created
OUTLIER_TYPE = 'Outlier Status'

# These are columns that are created by the tool but shouldn't be shown the user
INTERNAL_COLS = [
    OUTLIER_TYPE,
    IDX,
    FAILURES,
]


#
# Other
#

# Column name of any datetime column created by the tool
DATETIMECOL = 'DATETIME'

# Location of custom schema files
SCHEMA_DIR = 'outlier_tool/schemas'

# Location of icon files
ICONS_DIR = 'outlier_tool/icons'
DOTTED_BOX_ICON = os.path.join(ICONS_DIR, 'graph-selection-box.svg')
TRASH_ICON = os.path.join(ICONS_DIR, 'trash.svg')

# Sets the title of a user's browser tab
WINDOW_TITLE = 'Tool Prototype'

DEFAULT_THEME = shinyswatch.theme.darkly

# Threshold the tool can use to reject input files
MAX_FILE_SIZE_BYTES = 30_000_000
MAX_FILE_SIZE_MB = int(MAX_FILE_SIZE_BYTES / 1_000_000)

# Threshold the tool can use to warn the user about performance issues
WARN_FILE_SIZE_BYTES = 5_000_000
WARN_FILE_SIZE_MB = int(WARN_FILE_SIZE_BYTES / 1_000_000)

# Default option of file format selector
NO_FF = 'None'
