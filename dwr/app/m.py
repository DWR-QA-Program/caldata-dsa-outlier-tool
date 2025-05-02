#
# 'm' stands for miscellaneous variables: it is kept short to promote code
# readability at the expense of mild confusion upon first seeing it.
#
import shinyswatch

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
PASS = 'pass'

# Column name used by the app to denote a row's index
IDX = 'idx'

# Controls the graph's legend but also an internal column that gets created
OUTLIER_TYPE = 'Outlier Status'

# These are columns that are created by the tool but shouldn't be shown the user
INTERNAL_COLS = [
    OUTLIER_TYPE,
    IDX,
]


#
# Other
#

# Column name of any datetime column created by the tool
DATETIMECOL = 'DATETIME'

# Sets the title of a user's browser tab
WINDOW_TITLE = 'Tool Prototype'

DEFAULT_THEME = shinyswatch.theme.darkly
