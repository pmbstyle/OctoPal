from __future__ import annotations

import json

import structlog

from octopal.runtime.octo import followup_pipeline as _followup_pipeline

logger = structlog.get_logger(__name__)

_publish_runtime_metrics = _followup_pipeline._publish_runtime_metrics


class OctoOutputRuntimeMixin:
    @property
    def is_ws_active(self) -> bool:
        return self._ws_active

    def set_output_channel(
        self,
        is_ws: bool,
        send: callable | None = None,
        send_file: callable | None = None,
        progress: callable | None = None,
        worker_event: callable | None = None,
        typing: callable | None = None,
        owner_id: str | None = None,
        force: bool = False,
    ) -> bool:
        """Switch between Telegram and WebSocket output channels."""
        if is_ws:
            if self._ws_active and self._ws_owner and owner_id and self._ws_owner != owner_id:
                if force:
                    logger.warning(
                        "Forcing WebSocket channel takeover",
                        current_owner=self._ws_owner,
                        new_owner=owner_id,
                    )
                else:
                    logger.warning(
                        "Rejected WebSocket channel switch due to existing owner",
                        current_owner=self._ws_owner,
                        attempted_owner=owner_id,
                    )
                    return False
        else:
            if self._ws_owner and owner_id and self._ws_owner != owner_id:
                if force:
                    logger.warning(
                        "Forcing output channel reset from non-owner",
                        current_owner=self._ws_owner,
                        attempted_owner=owner_id,
                    )
                else:
                    logger.warning(
                        "Rejected output channel reset from non-owner",
                        current_owner=self._ws_owner,
                        attempted_owner=owner_id,
                    )
                    return False

        self._ws_active = is_ws
        if is_ws:
            self.internal_send = send
            self.internal_send_file = send_file
            self.internal_progress_send = progress
            self.internal_worker_event_send = worker_event
            self.internal_typing_control = typing
            self._ws_owner = owner_id or "ws-default"
            logger.info("Octo switched to WebSocket output channel")
        else:
            self.internal_send = self._tg_send
            self.internal_send_file = self._tg_send_file
            self.internal_progress_send = self._tg_progress
            self.internal_worker_event_send = self._tg_worker_event
            self.internal_typing_control = self._tg_typing
            self._ws_owner = None
            logger.info("Octo switched to Telegram output channel")

        # Update system status file if possible
        try:
            from octopal.infrastructure.config.settings import load_settings
            from octopal.runtime.state import _status_path, read_status

            settings = load_settings()
            status_data = read_status(settings) or {}
            status_data["active_channel"] = "WebSocket" if is_ws else "Telegram"
            _status_path(settings).write_text(
                json.dumps(status_data, indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.debug("Failed to update status file with active channel", exc_info=True)
        return True

    async def set_thinking(self, active: bool) -> None:
        """Toggle global thinking indicator."""
        if active:
            self._thinking_count += 1
        else:
            self._thinking_count = max(0, self._thinking_count - 1)
        _publish_runtime_metrics(self._thinking_count)

    async def set_typing(self, chat_id: int, active: bool):
        """Toggle typing indicator for a specific chat."""
        if self.internal_typing_control:
            try:
                await self.internal_typing_control(chat_id, active)
            except Exception:
                logger.debug(
                    "Failed to set typing status",
                    chat_id=chat_id,
                    active=active,
                    exc_info=True,
                )
