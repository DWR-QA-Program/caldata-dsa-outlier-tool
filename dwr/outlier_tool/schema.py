# Schemas are custom objects loaded from files that help the app load data more reliably.
import os
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from .m import SCHEMA_DIR
from .util import get_suffix

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
    columns: Optional[list[Column]]
    description: Optional[str] = ''
    file_format_description: Optional[str] = 'This file format has no description.'

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
        columns = [Column(**col) for col in data.get('columns', {})] # Unpack dict into Column constructor

        return cls(
            name=data['name'],
            description=data.get('description', ''),
            file_format_description=data.get('file_format_description', ''),
            columns=columns
        )


    @classmethod
    def from_file(cls, file_path: str | os.PathLike) -> 'Schema':
        '''Loads and parses a JSON file into a Schema instance.'''
        with open(file_path, 'r') as f:
            data = json.load(f)
        return cls.from_dict(data)

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
        print(f'COULD NOT LOAD SCHEMAS: {repr(e)}')
        return []


def get_schema(name):
    for s in SCHEMAS:
        if s.name == name:
            return s
    return None


def get_all_schema_names():
    return [s.name for s in SCHEMAS]


def get_file_format_info(name: str):
    if schema := get_schema(name):
        return schema.file_format_description
    else:
        return '''Currently, no file format is selected. Please ensure your uploaded file
            contains either one header row followed by your data, or just your data rows
            without a header. If you choose not to include a header, we'll create generic
            column names for you to use.
        '''



SCHEMAS = parse_schemas()
