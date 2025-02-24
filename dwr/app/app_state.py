import util

# Tracks the state of a user's session
class State():
    def __init__(self):
        self.files = {}

    def add_file(self, fname, df):
        self.files[fname] = File(fname, df)

    def get_file(self, fname):
        return self.files[fname]

    def get_filenames(self):
        return list(self.files.keys())


# Stores data needed for using an uploaded file
class File():
    def __init__(self, name, df):
        self.name = name
        self.df = df

        cols = list(self.df.columns)
        self.date_cols = util.get_date_cols(self.df)
        self.num_cols = util.get_num_cols(self.df)

        for col in self.date_cols:
            self.df[col] = self.df[col].apply(util.try_parse_date)

        self.last_selected_x_col = None
        self.last_selected_y_col = None
