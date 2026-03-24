"""Browser automation helpers used by runtime tools."""

from octopal.browser.manager import BrowserManager, get_browser_manager
from octopal.browser.snapshot import SnapshotResult, capture_aria_snapshot

__all__ = [
    "BrowserManager",
    "SnapshotResult",
    "capture_aria_snapshot",
    "get_browser_manager",
]
