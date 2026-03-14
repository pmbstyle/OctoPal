"""Compatibility shim for the historical broodmind.tools.tools import path."""

from broodmind.tools import catalog as _catalog
from broodmind.tools.catalog import get_tools

__all__ = ["get_tools"]


def __getattr__(name: str):
    return getattr(_catalog, name)
