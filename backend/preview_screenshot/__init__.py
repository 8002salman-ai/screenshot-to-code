"""screenshot_preview rendering: a pluggable backend behind a stable API.

Split for maintainability:
- ``base``               — the ``ScreenshotBackend`` interface + shared viewports
- ``playwright_backend`` — the default local-Chromium implementation
- ``registry``           — the active backend + the functions the app calls

Callers import everything they need straight from ``preview_screenshot``; the
internal module layout is an implementation detail.
"""

from preview_screenshot.base import ScreenshotBackend, VIEWPORT_SIZES
from preview_screenshot.registry import (
    capture_preview_screenshot,
    is_screenshot_preview_available,
    probe_screenshot_preview,
    set_screenshot_backend,
)


def __getattr__(name: str) -> object:
    # Lazily expose PlaywrightBackend so importing this package does not
    # require the playwright package to be installed (slim serverless deploys).
    if name == "PlaywrightBackend":
        from preview_screenshot.playwright_backend import PlaywrightBackend

        return PlaywrightBackend
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ScreenshotBackend",
    "VIEWPORT_SIZES",
    "capture_preview_screenshot",
    "is_screenshot_preview_available",
    "probe_screenshot_preview",
    "set_screenshot_backend",
]
