# Schemas are custom objects loaded from files that help the app load data more reliably.
import os
import json
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional
from .m import SCHEMA_DIR

@dataclass
class Column:
    '''Represents a column from a data dictionary.'''
    name: str
    type: str
    description: Optional[str] = None  # Optional field, defaults to None
    units: Optional[str] = None        # Optional field, defaults to None


@dataclass
class Schema:
    '''Class to hold information about a custom data schema.'''
    name: str
    description: Optional[str]
    columns: List[Column]


    @classmethod
    def from_dict(cls, data: dict) -> 'Schema':
        '''Creates a Schema object from a dictionary (parsed JSON).'''
        # Handle nested Column objects
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


def parse_schemas(loc=SCHEMA_DIR):
    try:
        return [
            Schema.from_file(fpath)
            for rootname, _, files in os.walk(loc, onerror=print)
            for filename in files
            if (fpath := Path(os.path.join(rootname, filename))).suffix == '.json'
        ]
    except Exception as e:
        print(e)
        return []


# TODO: make smarter
def find_matching_schema(df):
    cols = df.columns
    for schema in SCHEMAS:
        if len(cols) != len(schema.columns):
            continue
        return schema

SCHEMAS = parse_schemas()
