from typing import TYPE_CHECKING, Optional

from babel_cdn import normalize_babel_cdn
from preview_screenshot.base import ScreenshotBackend

if TYPE_CHECKING:
    from preview_screenshot.playwright_backend import PlaywrightBackend


def _default_backend() -> "ScreenshotBackend":
    """Create the default Playwright backend without importing playwright.

    Imported lazily so slim deployments (no playwright package) can boot and
    just report the screenshot-preview tool as unavailable via the probe.
    """
    from preview_screenshot.playwright_backend import PlaywrightBackend

    return PlaywrightBackend()


# The active backend. Defaults to local Chromium; a deployment can swap in an
# alternative (e.g. an external rendering API) via set_screenshot_backend.
_backend: ScreenshotBackend = _default_backend()

# Cached result of the startup probe: whether _backend can run here. None until
# the first probe runs. Used to gate the tool so it isn't offered when it can't.
_available: Optional[bool] = None


def set_screenshot_backend(backend: ScreenshotBackend) -> None:
    """Install the screenshot backend (call once, before the startup probe)."""
    global _backend
    _backend = backend


async def probe_screenshot_preview() -> bool:
    """Check (once, cached) whether the active backend can run here."""
    global _available
    if _available is None:
        _available = await _backend.available()
    return _available


def is_screenshot_preview_available() -> bool:
    """Synchronous accessor for the cached probe result.

    Defaults to True when the probe hasn't run yet so we never wrongly hide the
    tool before startup has checked; the runtime still fails safe if a call
    errors. In practice the startup probe sets this before any request.
    """
    return _available if _available is not None else True


async def capture_preview_screenshot(
    html: str,
    device: str = "desktop",
    full_page: bool = True,
) -> bytes:
    """Render HTML to PNG via the active backend.

    The public entry point the screenshot_preview tool calls; the backend choice
    is invisible to callers. Normalizes the Babel CDN first so generated React
    pages (old and new) actually mount before we capture.
    """
    return await _backend.capture(normalize_babel_cdn(html), device, full_page)
