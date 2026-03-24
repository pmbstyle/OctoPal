"""Compatibility shim for the historical octopal.tools.tools import path."""

from octopal.tools import catalog as _catalog
from octopal.tools.catalog import get_tools

__all__ = ["get_tools"]


def __getattr__(name: str):
    return getattr(_catalog, name)
