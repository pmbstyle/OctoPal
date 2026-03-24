# Octopal Hybrid Memory System

Octopal uses a sophisticated three-tier hybrid memory architecture designed to balance immediate conversational context, semantic retrieval of past events, and stable long-term knowledge ("Crystallization").

## 1. Architecture Overview

Memory is divided into three distinct layers:

| Layer | Storage | Retrieval Strategy | Purpose |
| :--- | :--- | :--- | :--- |
| **Temporal** | SQLite | Last N messages | Immediate conversational flow. |
| **Semantic** | SQLite + Vectors | Top-K Cosine Similarity | Recalling relevant past events/conversations. |
| **Canonical** | Filesystem (`.md`) | Hybrid (Inject + Search) | Crystallized knowledge, decisions, and lessons. |

---

## 2. The Canonical Layer (`memory/canon/`)

This is the "Stable" memory of the agent. Unlike the SQLite event store, the Canonical layer is curated by the Octo and is not subject to automatic expiration.

### Core Files
- `facts.md`: Verified truths about the user, project, or world.
- `decisions.md`: Architectural choices, policy rulings, and persistent preferences.
- `failures.md`: Lessons learned from errors to prevent repetition.

### Context Tiers
1. **Tier 1 (Automatic Injection):** `decisions.md` and `failures.md` are always injected into the Octo's system prompt (summarized if they exceed size limits).
2. **Tier 2 (Semantic Search):** The Octo uses the `search_canon` tool to query `facts.md` and other canon files when she needs specific details.

---

## 3. Decoupled Vector Storage

To ensure scalability and model independence, Octopal decouples text storage from the vector index.

- **Table `memory_entries`**: Stores the raw text, role, and metadata.
- **Table `memory_embeddings`**: Stores vectors mapped to entries by UUID, including the model name used for embedding.
- **Table `canon_embeddings`**: Stores semantic chunks of the canonical files for Tier 2 retrieval.

This allows for:
- **Re-embedding:** Switching embedding models without losing the original text.
- **Multi-model support:** Using different models for different types of retrieval.

---

## 4. The Memory Contract

Octopal enforces a strict hierarchy for writing to memory:

1. **Workers (Propose):** Workers cannot modify the Canon. They use the `propose_knowledge` tool to flag facts or lessons.
2. **Octo (Curate):** The Octo reviews worker proposals and her own experiences. She uses `manage_canon` to "crystallize" information into the `.md` files.
3. **Automatic (Log):** All raw interactions are automatically logged to the SQLite temporal/semantic store.

---

## 5. Maintenance & Guardrails

- **Compaction:** If a canonical file exceeds 4,000 characters, the `CanonService` issues a warning to the Octo, who is then responsible for summarizing and refactoring the file.
- **Cleanup:** Ephemeral SQLite memory is pruned according to settings (default: entries older than 30 days or exceeding 1,000 records). Canonical memory is **never** automatically deleted.

## 6. Quality Controls (Recent Improvements)

Octopal now applies additional quality controls in the transient/semantic memory pipeline:

- **Deduplication on Write:** Exact normalized duplicates in recent same-chat history are skipped to reduce noise.
- **Contradiction Tagging:** Simple assertion conflicts (for example, `X is Y` vs `X is not Y`) are flagged in metadata (`contradiction_detected`, `contradiction_with`) instead of silently treated as equal truth.
- **Confidence Scoring:** Entries carry a confidence value in metadata (role-defaulted and adjustable), which influences retrieval rank.
- **Recency Weighting:** Semantic retrieval applies a recency decay factor so newer relevant memories are favored while still retaining long-term recall.

These controls improve retrieval precision while preserving auditability of conflicting observations.
