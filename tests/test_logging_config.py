from broodmind.infrastructure.logging import _prepare_console_stream


class _FakeStream:
    def __init__(self, encoding: str = "cp1252", fail_utf8: bool = False):
        self.encoding = encoding
        self.fail_utf8 = fail_utf8
        self.calls: list[dict[str, str]] = []

    def reconfigure(self, **kwargs):
        self.calls.append(kwargs)
        encoding = kwargs.get("encoding")
        if encoding is not None:
            if self.fail_utf8 and encoding.lower() == "utf-8":
                raise OSError("utf-8 unavailable")
            self.encoding = encoding


def test_prepare_console_stream_prefers_utf8():
    stream = _FakeStream()

    result = _prepare_console_stream(stream)

    assert result is stream
    assert stream.encoding == "utf-8"
    assert stream.calls == [{"encoding": "utf-8", "errors": "backslashreplace"}]


def test_prepare_console_stream_falls_back_to_safe_errors():
    stream = _FakeStream(fail_utf8=True)

    result = _prepare_console_stream(stream)

    assert result is stream
    assert stream.calls == [
        {"encoding": "utf-8", "errors": "backslashreplace"},
        {"errors": "backslashreplace"},
    ]
