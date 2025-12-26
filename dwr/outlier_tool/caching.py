# Functions related to caching user preferences
# Caches are stored locally using diskcache
# Currently only stores test perferences per station

from __future__ import annotations

import atexit
import os
from pathlib import Path
from typing import Any

import diskcache as dc

# define exports
__all__ = [
    'LocalCache',
    'get_station_test_defaults',
    'set_station_test_defaults',
    'clear_station_test_defaults',
]

class LocalCache:
    """Class to manage local disk cache"""

    # create local cache with default of None
    _instance: dc.Cache | None = None

    # have it operate on the class level (cls)
    @classmethod
    def instance(cls) -> dc.Cache:
        if cls._instance is None:
            cache_dir = Path(os.getenv('APP_CACHE_DIR', 'cache')).resolve()
            cache_dir.mkdir(parents=True, exist_ok=True)
            cls._instance = dc.Cache(str(cache_dir), size_limit=int(6e9))
            atexit.register(cls.close)
        return cls._instance

    @classmethod
    def close(cls) -> None:
        if cls._instance is not None:
            cls._instance.close()
            cls._instance = None

# give namespace prefix for versioning
_PREFS_NS = 'prefs:v1'

# Helpers for storing/retrieving per-station test defaults
# The cache key is derived from Station_ID, test_key, and test_col and maps to a dict of
# {arg_id: value} (e.g., {'minimum': 1, 'maximum': 5}).

# Normalize the keys (fix case/whitespace)
def _norm_station_id(station_id: str) -> str:
    return str(station_id).strip().upper()

def _norm_test_key(test_key: str) -> str:
    return str(test_key).strip()

def _norm_col(test_col: str) -> str:
    return str(test_col).strip()

# Build the cache key
def _station_test_key(station_id: str, test_key: str, test_col: str) -> str:
    sid = _norm_station_id(station_id)
    tkey = _norm_test_key(test_key)
    col = _norm_col(test_col)
    return f'{_PREFS_NS}:station:{sid}:test:{tkey}:col:{col}'

# Look up defaults (if any)
def get_station_test_defaults(station_id: str, test_key: str, test_col: str) -> dict[str, Any] | None:
    cache = LocalCache.instance()
    return cache.get(_station_test_key(station_id, test_key, test_col), default=None)

# Store defaults; overwrite existing ones
def set_station_test_defaults(
    station_id: str,
    test_key: str,
    test_col: str,
    defaults: dict[str, Any],
) -> None:
    cache = LocalCache.instance()
    cache[_station_test_key(station_id, test_key, test_col)] = dict(defaults)

# Clear defaults when they're not set to anything
# TODO: make a "clear all defaults" button?
def clear_station_test_defaults(station_id: str, test_key: str, test_col: str) -> None:
    cache = LocalCache.instance()
    k = _station_test_key(station_id, test_key, test_col)
    try:
        del cache[k]
    except KeyError:
        pass
