from broodmind.channels.telegram import handlers as telegram_handlers


def test_is_duplicate_inbound_message_detects_replayed_message_id() -> None:
    telegram_handlers._RECENT_INBOUND_MESSAGE_IDS.clear()

    assert telegram_handlers._is_duplicate_inbound_message(42, 1001) is False
    assert telegram_handlers._is_duplicate_inbound_message(42, 1001) is True
    assert telegram_handlers._is_duplicate_inbound_message(42, 1002) is False


def test_prune_recent_inbound_messages_expires_old_entries() -> None:
    telegram_handlers._RECENT_INBOUND_MESSAGE_IDS.clear()
    telegram_handlers._RECENT_INBOUND_MESSAGE_IDS[(7, 11)] = 10.0
    telegram_handlers._RECENT_INBOUND_MESSAGE_IDS[(7, 12)] = 400.0

    telegram_handlers._prune_recent_inbound_messages(
        10.0 + telegram_handlers._INBOUND_MESSAGE_DEDUP_TTL_SECONDS + 1.0
    )

    assert (7, 11) not in telegram_handlers._RECENT_INBOUND_MESSAGE_IDS
    assert (7, 12) in telegram_handlers._RECENT_INBOUND_MESSAGE_IDS
