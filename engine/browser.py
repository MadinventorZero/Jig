"""Playwright browser automation with human-emulation helpers."""
import asyncio
import random
from typing import Optional


# ── Human emulation primitives ────────────────────────────────────────────────

async def human_type(page, selector: str, text: str) -> None:
    """Click a field and type with randomized inter-keystroke delays."""
    await page.click(selector)
    await page.fill(selector, '')
    for char in text:
        await page.type(selector, char, delay=random.randint(55, 130))
    await asyncio.sleep(random.uniform(0.15, 0.45))


async def human_click(page, selector: str) -> None:
    await asyncio.sleep(random.uniform(0.25, 0.65))
    await page.click(selector)
    await asyncio.sleep(random.uniform(0.15, 0.40))


async def human_select(page, selector: str, label: str) -> None:
    await asyncio.sleep(random.uniform(0.3, 0.6))
    await page.select_option(selector, label=label)
    await asyncio.sleep(random.uniform(0.2, 0.4))


async def detect_captcha(page) -> bool:
    """
    Return True only if an interactive CAPTCHA challenge is visible.
    Beverly Hills uses an invisible reCAPTCHA (size=invisible, badge=inline)
    that is always present in the HTML but never shows a challenge during form
    fill — only fires on submit. Keyword scanning the raw HTML produces a
    false positive; instead check for a visible, non-badge challenge frame.
    """
    try:
        return await page.evaluate("""() => {
            // reCAPTCHA: flag only frames that are NOT the invisible/badge variant
            for (const f of document.querySelectorAll('iframe[src*="recaptcha"]')) {
                const src = f.src || '';
                const invisible = src.includes('size=invisible') || src.includes('badge=');
                if (!invisible && f.offsetParent !== null) return true;
            }
            // hCaptcha visible challenge
            if (document.querySelector('.h-captcha iframe')) return true;
            return false;
        }""")
    except Exception:
        return False


# ── Browser session ───────────────────────────────────────────────────────────

class BookingBrowser:
    def __init__(self, headless: bool = False):
        self.headless  = headless
        self._pw       = None
        self._browser  = None
        self._page     = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *_):
        await self.stop()

    async def start(self) -> None:
        from playwright.async_api import async_playwright
        self._pw      = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.headless)
        context       = await self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        self._page = await context.new_page()

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    @property
    def page(self):
        return self._page

    async def run_booking(self, site_id: str, profile: dict, site_config: dict) -> dict:
        """Dispatch to the appropriate source module and return result dict."""
        if site_id == "beverly_hills":
            from sources.beverly_hills import fill_form, FORM_URL
            await self._page.goto(FORM_URL, wait_until='networkidle')
            await asyncio.sleep(random.uniform(1.0, 2.2))
            return await fill_form(self._page, profile, site_config)
        return {"ok": False, "error": f"Unknown site_id: {site_id}"}
