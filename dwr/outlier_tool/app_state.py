import pandas as pd

from . import upload_util
from .schema import get_schema


# Tracks the state of a user's session
class State:
    def __init__(self):
        self.files = {}

    def add_file(self, fname: str, df: pd.DataFrame, ff: str):
            # Single-file mode: a new upload replaces whatever was loaded before.
            # Remove this line to restore multi-file support.
            self.files.clear()
            self.files[fname] = File(fname, df, ff)
            return self.get_file(fname)

    def get_file(self, fname):
        return self.files[fname]

    def get_filenames(self):
        return list(self.files.keys())


# Stores data needed for using an uploaded file
class File:
    def __init__(self, name, df, selected_ff):
        self.name = name
        self.df = df
        self.schema = None
        self.composite_date_col = None
        self.last_selected_x_col = None
        self.last_selected_y_col = None
        self.od_results = {}  # (analyte, test_key) -> result entry
        self.manual_flags = {}  # analyte -> set of row indices
        self.flag_overrides = {}
        self.is_long = False
        self.analyte_col = None
        self.value_col = None
        

        # Match schema to file if possible
        if schema := get_schema(selected_ff):
            self.schema = schema

            if self.schema.columns:
                # Update df column names with schema's column names if file had no header
                if next(iter(df.columns)) == 'col0':
                    # This is only ever needed when a user has uploaded a file more than once,
                    # while toggling the header checkbox.
                    self.schema.reset_column_names()

                    self.df.rename(
                        {src: trg.name for src, trg in zip(df.columns, schema.columns, strict=False)},
                        axis='columns',
                        inplace=True,
                    )
                # Update schema column names to match what the file header is
                else:
                    for df_col, schema_col in zip(self.df.columns, self.schema.columns, strict=False):
                        schema_col.name = df_col

        self.empty_cols = upload_util.get_empty_cols(self.df)
        self.date_cols = upload_util.get_date_cols(self.df, self.empty_cols, self.schema)
        self.num_cols = upload_util.get_num_cols(self.df, self.empty_cols, self.schema)

        # Coerce numeric/string columns to date columns (this is a slow operation)
        for col in self.date_cols:
            # Inconsistent data can throw this operation off
            try:
                self.df[col] = self.df[col].apply(upload_util.try_parse_date)
            except TypeError as e:
                print(e)
                # TODO: get this info back to the user
            except Exception as e:
                print(e)

        # Remove date label from any supposed date columns that were not successfully converted
        self.date_cols = [
            col for col in self.date_cols if pd.api.types.is_datetime64_any_dtype(self.df[col])
        ]

        # Ensure column names are unique - this is needed for the 'check' tab since the
        # render function only accepts unique column names.
        df = upload_util.deduplicate_columns(df)

    # --- analyte resolution -------------------------------------------------
    # This is the one place the long/wide distinction lives on the way in. Every
    # caller below works with a plain series and never checks self.is_long.

    def get_analyte_names(self) -> list[str]:
        """Analytes available for testing, however the file happens to be shaped."""
        if self.is_long:
            return self.get_analytes()
        return list(self.num_cols)

    def get_analyte_mask(self, analyte: str) -> pd.Series:
        """Boolean mask of the rows belonging to an analyte.

        Wide files have one row per sampling event and one column per analyte, so
        every row belongs to every analyte and the mask is all True.
        """
        if not self.is_long or not self.analyte_col:
            return pd.Series(True, index=self.df.index)
        return self.df[self.analyte_col].astype(str).str.strip() == analyte

    def get_series(self, analyte: str, test_col: str = None) -> pd.Series:
        """Return the series a test should run on.

        `analyte` chooses the rows, `test_col` chooses the column. For most tests
        test_col is the analyte's own values; date-based tests (ts_col_type 'x')
        pass the date column instead, so that the timestamps are still restricted
        to the rows where this analyte was measured.
        """
        if self.is_long:
            col = test_col if test_col else self.value_col
            return self.df.loc[self.get_analyte_mask(analyte), col]

        col = test_col if test_col else analyte
        return self.df[col]

    # --- outlier detection results ------------------------------------------
    # Results are held here rather than as columns on self.df. Both file shapes
    # store them identically; flattening back onto the frame happens at export.

    def save_od_result(self, analyte, test_key, result=None, params=None, error=None):
        """Record one test run.

        `result` is the boolean series returned by the test, indexed by the rows it
        ran on. `error` is set instead when the test raised.
        """
        self.od_results[(analyte, test_key)] = {
            'result': result,
            'params': params or {},
            'error': error,
            'n_failed': int(result.sum()) if result is not None else None,
        }

    def get_od_result(self, analyte, test_key):
        return self.od_results.get((analyte, test_key))

    def get_od_results_for(self, analyte: str) -> dict:
        """Every test result for one analyte, keyed by test_key."""
        return {
            test_key: entry
            for (stored_analyte, test_key), entry in self.od_results.items()
            if stored_analyte == analyte
        }

    def clear_od_results(self):
        """Drop test results. Manual flags are user data and are left alone."""
        self.od_results.clear()

    # --- manual flags -------------------------------------------------------
    # Kept separate from od_results so that rerunning tests cannot discard them.

    def get_manual_flags(self, analyte: str) -> set:
        return self.manual_flags.get(analyte, set())

    def get_flag_overrides(self, analyte: str) -> set:
        return self.flag_overrides.get(analyte, set())

    def toggle_flag(self, analyte: str, indices, test_flagged) -> None:
        """Toggle points. A point currently showing as flagged gets cleared; one
        showing as clean gets manually flagged. `test_flagged` is the set of
        indices that tests currently flag, so the two cases can be told apart."""
        manual = self.manual_flags.setdefault(analyte, set())
        overrides = self.flag_overrides.setdefault(analyte, set())

        for idx in indices:
            if idx in manual:
                manual.discard(idx)
            elif idx in test_flagged and idx not in overrides:
                overrides.add(idx)
            elif idx in overrides:
                overrides.discard(idx)
            else:
                manual.add(idx)

    def get_flag_state(self, analyte: str) -> tuple[set, set]:
        return set(self.get_manual_flags(analyte)), set(self.get_flag_overrides(analyte))

    def set_flag_state(self, analyte: str, state: tuple[set, set]) -> None:
        manual, overrides = state
        self.manual_flags[analyte] = set(manual)
        self.flag_overrides[analyte] = set(overrides)

    def get_manual_flags(self, analyte: str) -> set:
        return self.manual_flags.get(analyte, set())

    def output_results_as_df(self):
        analyte_key = 'Analyte'
        test_key_col = 'Test name'
        numf_key = 'Data points that failed'

        data = {
            analyte_key: [],
            test_key_col: [],
            numf_key: [],
        }

        for (analyte, test_key), entry in self.od_results.items():
            data[analyte_key].append(analyte)
            data[test_key_col].append(test_key)
            data[numf_key].append(entry['error'] if entry['error'] else entry['n_failed'])
        return pd.DataFrame(data).sort_values([analyte_key, test_key_col])

    def get_analytes(self) -> list[str]:
        if not self.is_long or not self.analyte_col:
            return []
        if self.analyte_col not in self.df.columns:
            return []
        return sorted(
            self.df[self.analyte_col].dropna().astype(str).str.strip().unique().tolist()
        )