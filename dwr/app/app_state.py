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

        self.date_cols = upload_util.get_date_cols(self.df)
        self.num_cols = upload_util.get_num_cols(self.df)

        # Coerce numeric/string columns to date columns
        for col in self.date_cols:
            self.df[col] = self.df[col].apply(upload_util.try_parse_date)

        # Remove any supposed date columns that were not successfully converted
        self.date_cols = [col for col in self.date_cols if pd.api.types.is_datetime64_any_dtype(self.df[col])]

        if not self.date_cols:
            if all((replaced_columns := upload_util.attempt_composite_date(self.df))):
                self.composite_date_col = upload_util.DATETIMECOL
                self.date_cols.append(upload_util.DATETIMECOL)

                # Remove any numeric columns that contributed to the date since graphing
                # them would just be graphing a component of the x axis.
                for col in replaced_columns:
                    try:
                        self.num_cols.remove(col)
                    except ValueError:
                        pass
