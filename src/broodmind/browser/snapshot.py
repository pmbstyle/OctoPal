from __future__ import annotations

import re
from typing import Dict, List, Optional, Any, TypedDict
from playwright.async_api import Page
import structlog

logger = structlog.get_logger(__name__)

class ElementRef(TypedDict):
    role: str
    name: Optional[str]
    nth: int

class SnapshotResult(TypedDict):
    snapshot: str
    refs: Dict[str, ElementRef]

INTERACTIVE_ROLES = {
    "button", "link", "textbox", "checkbox", "radio", "combobox",
    "listbox", "menuitem", "option", "searchbox", "slider",
    "spinbutton", "switch", "tab", "treeitem"
}

def _get_indent_level(line: str) -> int:
    match = re.match(r"^(\s*)", line)
    return len(match.group(1)) // 2 if match else 0

async def capture_aria_snapshot(page: Page) -> SnapshotResult:
    """Capture an ARIA snapshot and inject stable references."""
    # Playwright's aria_snapshot returns a YAML-like string
    raw_snapshot = await page.aria_snapshot()
    lines = raw_snapshot.splitlines()
    
    result_lines = []
    refs: Dict[str, ElementRef] = {}
    
    # Track role+name counts to handle duplicates with nth()
    role_name_counts: Dict[str, int] = {}
    
    ref_counter = 1
    
    for line in lines:
        # Match pattern: "  - role "name"" or "  - role"
        match = re.match(r"^(\s*-\s*)(\w+)(?:\s+"([^"]*)")?(.*)$", line)
        if not match:
            result_lines.append(line)
            continue
            
        prefix, role, name, suffix = match.groups()
        role = role.lower()
        
        # We only assign refs to interactive roles or things with names
        if role in INTERACTIVE_ROLES or name:
            ref_id = f"e{ref_counter}"
            
            # Track duplicates
            key = f"{role}:{name or ''}"
            nth = role_name_counts.get(key, 0)
            role_name_counts[key] = nth + 1
            
            refs[ref_id] = {
                "role": role,
                "name": name,
                "nth": nth
            }
            
            # Inject ref into the snapshot line for the LLM
            ref_tag = f" [ref={ref_id}]"
            if nth > 0:
                ref_tag += f" [nth={nth}]"
                
            new_line = f"{prefix}{role}"
            if name:
                new_line += f' "{name}"'
            new_line += f"{ref_tag}{suffix}"
            result_lines.append(new_line)
            ref_counter += 1
        else:
            result_lines.append(line)
            
    return {
        "snapshot": "
".join(result_lines),
        "refs": refs
    }
