from playwright.async_api import async_playwright
from config import HEADLESS, PROFILE_DIR


class BrowserManager:
    def __init__(self):
        self.playwright = None
        self.context = None
        self.page = None

    async def start(self):
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)

        self.playwright = await async_playwright().start()

        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),

            headless=HEADLESS,

            slow_mo=80,

            viewport={
                "width": 1400,
                "height": 900,
            },

            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-gpu",
                "--start-maximized",
            ],
        )

        self.page = (
            self.context.pages[0]
            if self.context.pages
            else await self.context.new_page()
        )

        return self.page

    async def close(self):
        if self.context:
            await self.context.close()

        if self.playwright:
            await self.playwright.stop()