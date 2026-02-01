from __future__ import annotations


class Router:
    def should_delegate(self, text: str) -> bool:
        lowered = text.lower().strip()
        if lowered.startswith("/do"):
            return True
        keywords = ("fetch", "search", "download")
        return any(word in lowered for word in keywords)
