from playwright.sync_api import Browser, BrowserContext, Playwright

from config import (
    HEADLESS,
    LOCALE,
    USER_AGENT,
    VIEWPORT_HEIGHT,
    VIEWPORT_WIDTH,
)


def create_browser(playwright: Playwright) -> Browser:
    return playwright.chromium.launch(
        headless=HEADLESS
    )


def create_context(browser: Browser) -> BrowserContext:
    return browser.new_context(
        viewport={
            "width": VIEWPORT_WIDTH,
            "height": VIEWPORT_HEIGHT,
        },
        locale=LOCALE,
        user_agent=USER_AGENT,
    )