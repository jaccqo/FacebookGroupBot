import os
import asyncio
import traceback

from dotenv import load_dotenv

from browser import BrowserManager
from bot import FacebookBot
from db import (
    init_db,
    save_group,
    get_group_by_url,
)

load_dotenv()

SLEEP_SECONDS = int(os.getenv("SLEEP_SECONDS", 21600))  # 6 hours
RUN_MODE = os.getenv("RUN_MODE", "scrape").strip().lower()
SEARCH_QUERY = os.getenv("SEARCH_QUERY", "ישראלים ב")
SINGLE_GROUP_URL = os.getenv("SINGLE_GROUP_URL", "").strip()


class App:
    def __init__(self):
        self.browser = BrowserManager()
        self.bot = None

    async def setup(self):
        await init_db()

        page = await self.browser.start()
        self.bot = FacebookBot(page)

        await self.bot.start()

    async def close(self):
        await self.browser.close()

    async def process_group(self, group: dict):
        await save_group(group)

        print("-" * 80)
        print(group.get("name"))
        print(group.get("meta"))
        print(group.get("url"))
        print("Saved.")

        already_joined = bool(group.get("joined"))

        if already_joined:
            print("Already joined. Skipping join step.")
            joined = True
        else:
            joined = await self.bot.join_group_from_link(group)

        if not joined:
            return

        members_page = await self.bot.open_group_members_page(group)

        if not members_page:
            return

        try:
            await self.bot.scroll_and_process_members(
                members_page,
                group,
                max_scrolls=40,
            )
        finally:
            await members_page.close()

    async def scrape_groups(self, query: str):
        await self.bot.search_groups(query)

        await self.bot.scroll_and_process_groups(
            on_group=self.process_group,
            max_scrolls=40,
        )

    async def join_single_group(self, url: str):
        existing = await get_group_by_url(url)

        if existing:
            print("Group found in DB.")
            group = existing
        else:
            print("Group not found in DB. Creating temp record.")

            group = {
                "name": "Manual group",
                "url": url,
                "meta": "",
                "raw_text": "",
                "joined": 0,
            }

            await save_group(group)

        await self.process_group(group)

    async def run_cycle(self):
        await self.setup()

        if RUN_MODE == "single":
            if not SINGLE_GROUP_URL:
                print("SINGLE_GROUP_URL is missing in .env")
                return

            await self.join_single_group(SINGLE_GROUP_URL)

        else:
            await self.scrape_groups(SEARCH_QUERY)

    async def run_forever(self):
        while True:
            try:
                await self.run_cycle()

            except KeyboardInterrupt:
                print("Stopped by user.")
                break

            except Exception:
                print("Bot crashed:")
                traceback.print_exc()

            finally:
                try:
                    await self.close()
                except Exception:
                    pass

            print(f"\n😴 Sleeping for {SLEEP_SECONDS} seconds...\n")
            await asyncio.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    asyncio.run(App().run_forever())