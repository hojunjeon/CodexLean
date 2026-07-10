from __future__ import annotations

from .generic import GenericFilter
from .git_output import GitDiffFilter, GitLogFilter, GitStatusFilter
from .json_output import JsonFilter
from .log_output import LogFilter
from .search_output import SearchFilter
from .test_output import TestFilter
from .tree_output import TreeFilter

_FILTERS = {
    "generic": GenericFilter(),
    "test": TestFilter(),
    "log": LogFilter(),
    "json": JsonFilter(),
    "git_status": GitStatusFilter(),
    "git_diff": GitDiffFilter(),
    "git_log": GitLogFilter(),
    "search": SearchFilter(),
    "tree": TreeFilter(),
}


def get_filter(kind: str):
    return _FILTERS.get(kind, _FILTERS["generic"])


__all__ = ["get_filter"]
