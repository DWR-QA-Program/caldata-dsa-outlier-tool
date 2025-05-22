# Schemas are custom objects loaded from files that help the app load data more reliably.
import os
import json
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

from .m import SCHEMA_DIR

# We need a "sentinel" object to allow None as a valid optional argument
_sentinel = object()

# List possible data types specified in schema files
_NUMERIC = ('int', 'float')
_DATETIME = ('datetime',)


@dataclass
class Column:
    '''Represents a column from a data dictionary.'''
    name: str
    type: str
    description: Optional[str] = None # Optional field, defaults to None
    units: Optional[str] = None
    min: Optional[int | float] = None
    max: Optional[int | float] = None
    _orig_name: str = None # stores original column name from file

    def __post_init__(self):
        self._orig_name = self.name

    def reset_name(self):
        self.name = self._orig_name

    def is_numeric(self):
        return self.type in _NUMERIC

    def is_datetime(self):
        return self.type in _DATETIME


# TODO: json schema validation
@dataclass
class Schema:
    '''Class to hold information about a custom data schema.'''
    name: str
    description: Optional[str]
    columns: List[Column]

    # Support list-type indexing
    def __getitem__(self, idx):
        return self.columns[idx]

    # Support dictionary-type get method
    def get(self, k, default_value=_sentinel):
        for col in self.columns:
            if col.name == k:
                return col
        if default_value is not _sentinel:
            return default_value
        raise ValueError(str(k))


    @classmethod
    def from_dict(cls, data: dict) -> 'Schema':
        '''Creates a Schema object from a dictionary (parsed JSON).'''
        columns = [Column(**col) for col in data['columns']] # Unpack dict into Column constructor

        return cls(
            name=data['name'],
            description=data.get('description', ''),
            columns=columns
        )


    @classmethod
    def from_file(cls, file_path: str | os.PathLike) -> 'Schema':
        '''Loads and parses a JSON file into a Schema instance.'''
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            return cls.from_dict(data)
        except FileNotFoundError:
            print(f'ERROR: File not found: {file_path}')
        except json.JSONDecodeError:
            print(f'ERROR: Could not decode JSON from {file_path}')
        except Exception as e:
            print(f'ERROR: {e}')

    def reset_column_names(self):
        for col in self.columns:
            col.reset_name()


def parse_schemas(loc=SCHEMA_DIR):
    try:
        return [
            Schema.from_file(fpath)
            for rootname, _, files in os.walk(loc, onerror=print)
            for filename in files
            if (fpath := Path(os.path.join(rootname, filename))).suffix == '.json'
        ]
    except Exception as e:
        print(f'COULD NOT LOAD SCHEMAS: {e}')
        return []


# TODO: make smarter
def find_matching_schema(df):
    cols = df.columns
    for schema in SCHEMAS:
        if len(cols) != len(schema.columns):
            continue
        return schema

SCHEMAS = parse_schemas()
