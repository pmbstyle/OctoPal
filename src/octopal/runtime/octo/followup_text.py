from __future__ import annotations

import re

import structlog

from octopal.runtime.octo.context_reset import _normalize_compact
from octopal.runtime.octo.delivery import resolve_user_delivery
from octopal.runtime.octo.router import normalize_plain_text

logger = structlog.get_logger(__name__)


def _merge_worker_followup_texts(texts: list[str]) -> str:
    merged: list[str] = []
    seen: set[str] = set()
    for raw_text in texts:
        text = normalize_plain_text(raw_text)
        if not resolve_user_delivery(text).user_visible:
            continue
        fingerprint = text.casefold()
        if fingerprint in seen:
            continue
        replacement_index: int | None = None
        should_skip = False
        for idx, existing in enumerate(merged):
            overlap = _worker_followup_overlap(existing, text)
            if overlap == "existing_contains_new":
                logger.info(
                    "Dropped overlapping worker follow-up",
                    kept_len=len(existing),
                    dropped_len=len(text),
                    reason="existing_contains_new",
                )
                should_skip = True
                break
            if overlap == "new_contains_existing":
                logger.info(
                    "Replacing overlapping worker follow-up",
                    prior_len=len(existing),
                    replacement_len=len(text),
                    reason="new_contains_existing",
                )
                replacement_index = idx
                break
        if should_skip:
            continue
        seen.add(fingerprint)
        if replacement_index is not None:
            prior = merged[replacement_index]
            seen.discard(prior.casefold())
            merged[replacement_index] = text
        else:
            merged.append(text)
    if not merged:
        return ""
    if len(merged) == 1:
        return merged[0]
    return "\n\n".join(merged)


def _worker_followup_overlap(existing: str, candidate: str) -> str | None:
    existing_norm = _normalize_compact(existing)
    candidate_norm = _normalize_compact(candidate)
    if not existing_norm or not candidate_norm:
        return None
    if existing_norm == candidate_norm:
        return "existing_contains_new"
    if existing_norm in candidate_norm:
        return "new_contains_existing"
    if candidate_norm in existing_norm:
        return "existing_contains_new"

    existing_words = set(_worker_followup_keywords(existing_norm))
    candidate_words = set(_worker_followup_keywords(candidate_norm))
    if len(existing_words) < 12 or len(candidate_words) < 12:
        return None

    shared = existing_words.intersection(candidate_words)
    if not shared:
        return None

    containment = len(shared) / float(min(len(existing_words), len(candidate_words)))
    if containment < 0.72:
        return None

    if len(candidate_norm) >= int(len(existing_norm) * 1.2):
        return "new_contains_existing"
    if len(existing_norm) >= int(len(candidate_norm) * 1.2):
        return "existing_contains_new"
    return None


def _worker_followup_keywords(value: str) -> list[str]:
    return re.findall(r"\w+", value, flags=re.UNICODE)
