from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher

from broodmind.config.settings import Settings
from broodmind.memory.service import MemoryService
from broodmind.policy.engine import PolicyEngine
from broodmind.providers.openai_embeddings import OpenAIEmbeddingsProvider
from broodmind.providers.zai import ZAIProvider
from broodmind.queen.core import Queen
from broodmind.store.sqlite import SQLiteStore
from broodmind.telegram.approvals import ApprovalManager
from broodmind.telegram.handlers import register_handlers
from broodmind.workers.launcher_factory import build_launcher
from broodmind.workers.runtime import WorkerRuntime

logger = logging.getLogger(__name__)


def build_dispatcher(settings: Settings, bot: Bot) -> Dispatcher:
    provider = ZAIProvider(settings)
    store = SQLiteStore(settings)
    policy = PolicyEngine()
    launcher = build_launcher(settings)
    runtime = WorkerRuntime(
        store=store,
        policy=policy,
        workspace_dir=settings.workspace_dir,
        launcher=launcher,
    )
    approvals = ApprovalManager(bot=bot)
    embeddings = None
    if settings.openai_api_key:
        embeddings = OpenAIEmbeddingsProvider(settings)
    memory = MemoryService(
        store=store,
        embeddings=embeddings,
        top_k=settings.memory_top_k,
        min_score=settings.memory_min_score,
        max_chars=settings.memory_max_chars,
    )
    queen = Queen(
        provider=provider,
        store=store,
        policy=policy,
        runtime=runtime,
        approvals=approvals,
        memory=memory,
    )

    dp = Dispatcher()
    register_handlers(dp, queen, approvals, settings)
    return dp


async def run_bot(settings: Settings) -> None:
    bot = Bot(token=settings.telegram_bot_token)
    dp = build_dispatcher(settings, bot)

    logger.info("Starting Telegram polling")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
