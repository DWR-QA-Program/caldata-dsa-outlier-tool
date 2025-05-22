import pandas as pd
from shiny import ui

from . import m
from . import util
from . import upload_util
from .schema import find_matching_schema

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
        self.schema = None
        self.composite_date_col = None
        self.last_selected_x_col = None
        self.last_selected_y_col = None
        self.od_results = {}


        # Match schema to file if possible
        if schema := find_matching_schema(self.df):
            self.schema = schema

            # Update df column names with schema's column names if file had no header
            if list(df.columns)[0] == 'col0':
                # This is only ever needed when a user has uploaded a file more than once,
                # while toggling the header checkbox.
                self.schema.reset_column_names()

                self.df.rename(
                    {src: trg.name for src, trg in zip(df.columns, schema.columns)},
                    axis='columns',
                    inplace=True,
                )
            # Update schema column names to match what the file header is
            else:
                for df_col, schema_col in zip(self.df.columns, self.schema.columns):
                    schema_col.name = df_col


        self.empty_cols = upload_util.get_empty_cols(self.df)
        self.date_cols = upload_util.get_date_cols(self.df, self.empty_cols, self.schema)
        self.num_cols = upload_util.get_num_cols(self.df, self.empty_cols, self.schema)

        # Coerce numeric/string columns to date columns
        for col in self.date_cols:
            self.df[col] = self.df[col].apply(upload_util.try_parse_date)

        # Remove date label from any supposed date columns that were not successfully converted
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

        # Ensure column names are unique - this is needed for the 'check' tab since the
        # render function only accepts unique column names.
        df = upload_util.deduplicate_columns(df)


    def save_od_result(self, test_name, test_col, result):
        results = self.od_results
        if test_name not in results:
            results[test_name] = {}
        results[test_name][test_col] = result


    def output_results_as_df(self):
        col_key = 'Column'
        test_key = 'Test name'
        numf_key = 'Number of failures'

        data = {
            col_key: [],
            test_key: [],
            numf_key: [],
        }

        for test_name in self.od_results:
            for test_col in self.od_results[test_name]:
                data[col_key].append(test_col)
                data[test_key].append(test_name)
                data[numf_key].append(self.od_results[test_name][test_col])
        return pd.DataFrame(data).sort_values([col_key, test_key])#.fillna('N/A')
