from __future__ import annotations

import asyncio
from pathlib import Path

from octopal.infrastructure.store.sqlite import SQLiteStore
from octopal.runtime.memory.canon import CanonService
from octopal.runtime.memory.facts import FactsService
from octopal.runtime.memory.service import MemoryService


class _StoreSettings:
    def __init__(self, state_dir: Path, workspace_dir: Path) -> None:
        self.state_dir = state_dir
        self.workspace_dir = workspace_dir


def test_memory_service_records_fact_candidates_in_store(tmp_path: Path) -> None:
    store = SQLiteStore(_StoreSettings(tmp_path / "data", tmp_path / "workspace"))
    facts = FactsService(store=store, owner_id="default")
    service = MemoryService(store=store, embeddings=None, owner_id="default", facts=facts)

    async def scenario() -> None:
        await service.add_message("assistant", "Service is healthy.", {"chat_id": 7})

    asyncio.run(scenario())
    rows = store.list_memory_facts("default", status="candidate", limit=20)
    assert len(rows) == 1
    assert rows[0].subject == "service"
    assert rows[0].value_text == "healthy"
    assert rows[0].source_kind == "memory"

    sources = store.list_memory_fact_sources(rows[0].id)
    assert len(sources) == 1
    assert sources[0].memory_entry_uuid is not None


def test_canon_service_syncs_verified_facts(tmp_path: Path) -> None:
    store = SQLiteStore(_StoreSettings(tmp_path / "data", tmp_path / "workspace"))
    facts = FactsService(store=store, owner_id="default")
    canon = CanonService(
        workspace_dir=tmp_path / "workspace",
        store=store,
        embeddings=None,
        facts=facts,
    )

    async def scenario() -> None:
        await canon.write_canon("facts", "# Facts\n\nService is healthy.\n", "overwrite")

    asyncio.run(scenario())
    rows = store.list_memory_facts(
        "default",
        status="active",
        source_kind="canon",
        source_ref="facts.md",
        limit=20,
    )
    assert len(rows) == 1
    assert rows[0].subject == "service"
    assert rows[0].value_text == "healthy"


def test_facts_service_returns_relevant_active_facts(tmp_path: Path) -> None:
    store = SQLiteStore(_StoreSettings(tmp_path / "data", tmp_path / "workspace"))
    facts = FactsService(store=store, owner_id="default")
    canon = CanonService(
        workspace_dir=tmp_path / "workspace",
        store=store,
        embeddings=None,
        facts=facts,
    )

    async def scenario() -> None:
        await canon.write_canon("decisions", "# Decisions\n\nPrimary installer is uv.\n", "overwrite")

    asyncio.run(scenario())
    context = facts.get_relevant_facts(
        "what did we decide about installer?",
        memory_facets=["decision"],
        limit=3,
    )
    assert len(context) == 1
    assert "primary installer is uv" in context[0]
