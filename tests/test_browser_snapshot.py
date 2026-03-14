from __future__ import annotations

import asyncio

from broodmind.browser.snapshot import _get_indent_level, capture_aria_snapshot


class _PageStub:
    def __init__(self, snapshot: str) -> None:
        self._snapshot = snapshot

    async def aria_snapshot(self) -> str:
        return self._snapshot


def test_get_indent_level_counts_two_space_steps() -> None:
    assert _get_indent_level("") == 0
    assert _get_indent_level("  - button") == 1
    assert _get_indent_level("    - link") == 2


def test_capture_aria_snapshot_injects_refs_and_tracks_duplicates() -> None:
    page = _PageStub(
        "\n".join(
            [
                '- heading "Main settings"',
                '- button "Save" [disabled]',
                '- button "Save"',
                '- paragraph',
                '- img "Logo"',
            ]
        )
    )

    result = asyncio.run(capture_aria_snapshot(page))

    assert result["snapshot"].splitlines() == [
        '- heading "Main settings" [ref=e1]',
        '- button "Save" [ref=e2] [disabled]',
        '- button "Save" [ref=e3] [nth=1]',
        "- paragraph",
        '- img "Logo" [ref=e4]',
    ]
    assert result["refs"] == {
        "e1": {"role": "heading", "name": "Main settings", "nth": 0},
        "e2": {"role": "button", "name": "Save", "nth": 0},
        "e3": {"role": "button", "name": "Save", "nth": 1},
        "e4": {"role": "img", "name": "Logo", "nth": 0},
    }


def test_capture_aria_snapshot_preserves_unmatched_lines() -> None:
    page = _PageStub(
        "\n".join(
            [
                "RootWebArea",
                "  - text: plain text",
                '  - link "Docs"',
            ]
        )
    )

    result = asyncio.run(capture_aria_snapshot(page))

    assert result["snapshot"].splitlines() == [
        "RootWebArea",
        "  - text: plain text",
        '  - link "Docs" [ref=e1]',
    ]
    assert result["refs"] == {
        "e1": {"role": "link", "name": "Docs", "nth": 0},
    }
