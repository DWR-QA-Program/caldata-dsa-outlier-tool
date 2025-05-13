import pandas as pd

from outlier_tool.upload_util import deduplicate_columns


class TestDedupeColumns:
    def test_nochange(self):
        columns = ['a', 'b', 'c', 'd']
        data = [list(range(len(columns)))]
        df = pd.DataFrame(data, columns=columns)
        df = deduplicate_columns(df)
        assert list(df.columns) == columns

    def test_one_dedupe(self):
        columns = ['a', 'b', 'c', 'c']
        data = [list(range(len(columns)))]
        df = pd.DataFrame(data, columns=columns)
        df = deduplicate_columns(df)
        assert list(df.columns) == ['a', 'b', 'c', 'c_1']

    def test_multiple_dedupe(self):
        columns = ['a', 'a', 'b', 'c', 'c', 'c']
        data = [list(range(len(columns)))]
        df = pd.DataFrame(data, columns=columns)
        df = deduplicate_columns(df)
        assert list(df.columns) == ['a', 'a_1', 'b', 'c', 'c_1', 'c_2']

    def test_underscore_nochange(self):
        columns = ['a_0', 'b_1', 'c_2', 'c_5']
        data = [list(range(len(columns)))]
        df = pd.DataFrame(data, columns=columns)
        df = deduplicate_columns(df)
        assert list(df.columns) == columns

    def test_complex_dedupe(self):
        columns = ['a', 'a', 'a_1', 'a_2', 'b', 'b_1', 'b']
        data = [list(range(len(columns)))]
        df = pd.DataFrame(data, columns=columns)
        df = deduplicate_columns(df)
        assert list(df.columns) == ['a', 'a_1', 'a_2', 'a_3', 'b', 'b_1', 'b_2']

if __name__ == '__main__':
    unittest.main()
