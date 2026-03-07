from broodmind.cli.configure import _saved_summary_next_steps


def test_saved_summary_next_steps_for_whatsapp() -> None:
    steps = _saved_summary_next_steps("whatsapp")

    assert steps == [
        "uv run broodmind whatsapp install-bridge",
        "uv run broodmind whatsapp link",
        "uv run broodmind start",
        "uv run broodmind whatsapp status",
    ]


def test_saved_summary_next_steps_for_telegram() -> None:
    steps = _saved_summary_next_steps("telegram")

    assert steps == [
        "uv run broodmind start",
        "uv run broodmind status",
        "uv run broodmind config show",
    ]
