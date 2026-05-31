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

            viewport={
                "width": 1366,
                "height": 768,
            },

            screen={
                "width": 1366,
                "height": 768,
            },

            device_scale_factor=1,
            is_mobile=False,
            has_touch=False,

            locale="en-US",
            timezone_id="America/New_York",

            slow_mo=60,

            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-gpu",
                "--window-size=900,700",
            ],
        )

        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = await self.context.new_page()

        await self.page.set_viewport_size({
            "width": 900,
            "height": 700,
        })

        return self.page

    async def close(self):
        if self.context:
            await self.context.close()
            self.context = None

        if self.playwright:
            await self.playwright.stop()
            self.playwright = None