import pandas as pd
from shiny import ui
import util
import upload_util

# Tracks the state of a user's session
class State():
    def __init__(self):
        self.files = {}

    def add_file(self, fname, df):
        self.files[fname] = File(fname, df)
        return self.get_file(fname)

    def get_file(self, fname):
        return self.files[fname]

    def get_filenames(self):
        return list(self.files.keys())


# Stores data needed for using an uploaded file
class File():
    def __init__(self, name, df):
        self.name = name
        self.df = df
        self.composite_date_col = None
        self.last_selected_x_col = None
        self.last_selected_y_col = None
        self.od_results = {}

        self.date_cols = upload_util.get_date_cols(self.df)
        self.num_cols = upload_util.get_num_cols(self.df)
        self.ph_cols = []

        # Coerce numeric/string columns to date columns
        for col in self.date_cols:
            self.df[col] = self.df[col].apply(upload_util.try_parse_date)

        # Remove any supposed date columns that were not successfully converted
        self.date_cols = [col for col in self.date_cols if pd.api.types.is_datetime64_any_dtype(self.df[col])]

        if not self.date_cols:
            if all((replaced_columns := upload_util.attempt_composite_date(self.df))):
                self.composite_date_col = m.DATETIMECOL
                self.date_cols.append(m.DATETIMECOL)

                # Remove any numeric columns that contributed to the date since graphing
                # them would just be graphing a component of the x axis.
                for col in replaced_columns:
                    try:
                        self.num_cols.remove(col)
                    except ValueError:
                        pass


    def save_od_result(self, test_name, x_col, y_col, result):
        results = self.od_results
        if test_name not in results:
            results[test_name] = {}
        if x_col not in results[test_name]:
            results[test_name][x_col] = {}

        results[test_name][x_col][y_col] = result


    def get_result(self, test_name, x_col, y_col):
        try:
            return self.results[test_name][x_col][y_col]
        except KeyError:
            return None

    def format_results(self):
        ret = ui.TagList()
        for test_name in self.od_results:
            for x_col in self.od_results[test_name]:
                for y_col in self.od_results[test_name][x_col]:
                    result = self.od_results[test_name][x_col][y_col]
                    if isinstance(result, int):
                        ret.append(ui.p(f'{test_name}: {x_col}, {y_col}: {result} outliers'))
                    else: # an error ocurred
                        ret.append(ui.p(f'{test_name}: {x_col}, {y_col}: {result}'))
        return ui.HTML(ret)

