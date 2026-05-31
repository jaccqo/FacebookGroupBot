import os
import json
import random
from pathlib import Path

from dotenv import load_dotenv

from auth import login
from ai import ask_ai_for_group_answer
from db import (
    mark_group_joined,
    update_group_status,
    save_group_member,
    has_member_been_messaged,
    mark_member_message_drafted,
    mark_member_message_sent,
)
import time

load_dotenv()

FB_NAME = os.getenv("FB_NAME", "").strip().lower()


def env_int(name: str, default: int):
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def env_bool(name: str, default: bool):
    value = os.getenv(name, str(default)).strip().lower()

    return value in (
        "1",
        "true",
        "yes",
        "y",
        "on",
    )

SKIP_ADMINS = env_bool("SKIP_ADMINS", True)
SKIP_MODERATORS = env_bool("SKIP_MODERATORS", False)
SKIP_VERIFIED = env_bool("SKIP_VERIFIED", False)

GROUP_COOLDOWN_MIN = env_int("GROUP_COOLDOWN_MIN", 8)
GROUP_COOLDOWN_MAX = env_int("GROUP_COOLDOWN_MAX", 18)

MEMBER_COOLDOWN_MIN = env_int("MEMBER_COOLDOWN_MIN", 20)
MEMBER_COOLDOWN_MAX = env_int("MEMBER_COOLDOWN_MAX", 45)

PROFILE_COOLDOWN_MIN = env_int("PROFILE_COOLDOWN_MIN", 5)
PROFILE_COOLDOWN_MAX = env_int("PROFILE_COOLDOWN_MAX", 12)

SCROLL_COOLDOWN_MIN = env_int("SCROLL_COOLDOWN_MIN", 2)
SCROLL_COOLDOWN_MAX = env_int("SCROLL_COOLDOWN_MAX", 5)


class FacebookBot:
    def __init__(self, page):
        self.page = page

    async def cooldown(self, page, label: str, min_seconds: int, max_seconds: int):
        seconds = random.randint(min_seconds, max_seconds)
        print(f"Cooldown [{label}]: {seconds}s")
        await page.wait_for_timeout(seconds * 1000)

    async def start(self):
        await login(self.page)

    async def search_top(self, query: str):
        search_input = self.page.locator(
            "input[aria-label='Search Facebook'][type='search']"
        ).first

        await search_input.wait_for(timeout=15000)
        await search_input.click()
        await search_input.fill(query)
        await search_input.press("Enter")

        print(f"Searched Facebook for: {query}")
        await self.page.wait_for_timeout(6000)

    async def click_see_all_groups(self):
        see_all = self.page.locator(
            "a[aria-label='See all'][href*='/search/groups/']"
        ).first

        await see_all.wait_for(timeout=15000)
        await see_all.click()

        print("Clicked groups See all.")
        await self.page.wait_for_timeout(5000)

    async def search_groups(self, query: str):
        await self.search_top(query)
        await self.click_see_all_groups()

    async def extract_visible_groups(self):
        groups = await self.page.evaluate("""
        () => {
            const results = [];

            const links = Array.from(
                document.querySelectorAll("a[href*='/groups/']")
            );

            for (const link of links) {
                const href = link.href;
                const name = link.innerText?.trim() || link.getAttribute("aria-label") || "";

                if (!href || !name) continue;
                if (name.startsWith("Profile photo of")) continue;

                const article = link.closest("[role='article']");
                if (!article) continue;

                const text = article.innerText || "";

                const metaLine = text
                    .split("\\n")
                    .find(line =>
                        line.includes("members") ||
                        line.includes("Public") ||
                        line.includes("Private")
                    ) || "";

                results.push({
                    name,
                    url: href.split("?")[0],
                    meta: metaLine.trim(),
                    raw_text: text.trim()
                });
            }

            return results;
        }
        """)

        cleaned = {}

        for group in groups:
            url = group.get("url", "").strip()

            if not url:
                continue

            if "/groups/" not in url:
                continue

            if url not in cleaned:
                cleaned[url] = group

        return list(cleaned.values())

    async def scroll_and_process_groups(self, on_group, max_scrolls: int = 30):
        seen_urls = set()
        same_count_rounds = 0
        last_seen_count = 0

        for i in range(max_scrolls):
            visible_groups = await self.extract_visible_groups()
            new_groups = []

            for group in visible_groups:
                url = group.get("url", "").strip()

                if not url:
                    continue

                if url in seen_urls:
                    continue

                seen_urls.add(url)
                new_groups.append(group)

            for group in new_groups:
                await on_group(group)

                await self.cooldown(
                    self.page,
                    "after group",
                    GROUP_COOLDOWN_MIN,
                    GROUP_COOLDOWN_MAX,
                )

            print(
                f"Scroll {i + 1}: new={len(new_groups)} total={len(seen_urls)}"
            )

            if len(seen_urls) == last_seen_count:
                same_count_rounds += 1
            else:
                same_count_rounds = 0

            if same_count_rounds >= 4:
                print("No new groups found. Stopping scroll.")
                break

            last_seen_count = len(seen_urls)

            await self.page.mouse.wheel(0, 2500)
            await self.cooldown(
                self.page,
                "groups scroll down",
                SCROLL_COOLDOWN_MIN,
                SCROLL_COOLDOWN_MAX,
            )

            await self.page.mouse.wheel(0, -500)
            await self.page.wait_for_timeout(700)

            await self.page.mouse.wheel(0, 1800)
            await self.cooldown(
                self.page,
                "groups scroll continue",
                SCROLL_COOLDOWN_MIN,
                SCROLL_COOLDOWN_MAX,
            )

    async def open_group_members_page(self, group: dict):
        url = group["url"].rstrip("/")
        members_url = f"{url}/members"

        page = await self.page.context.new_page()

        try:
            await page.goto(members_url, wait_until="domcontentloaded")
            await page.wait_for_url("**/members**", timeout=15000)
            await page.wait_for_timeout(4000)

            print(f"Opened members page: {page.url}")
            return page

        except Exception as e:
            print(f"Failed opening members page for {group['name']}: {e}")
            await page.close()
            return None

    async def extract_visible_members(self, page):
        members = await page.evaluate("""
        () => {
            const results = [];

            const links = Array.from(
                document.querySelectorAll('a[href*="/user/"]')
            );

            for (const link of links) {
                const href = link.href;
                const name = (link.innerText || link.getAttribute("aria-label") || "").trim();

                if (!href || !name) continue;

                const card =
                    link.closest('[role="listitem"]') ||
                    link.closest('[data-visualcompletion="ignore-dynamic"]');

                if (!card) continue;

                const rawText = (card.innerText || "").trim();

                if (!rawText) continue;

                const lines = rawText
                    .split("\\n")
                    .map(line => line.trim())
                    .filter(Boolean);

                results.push({
                    name,
                    url: href.split("?")[0],
                    raw_text: rawText,
                    lines,
                    is_admin: rawText.includes("Admin"),
                    is_moderator: rawText.includes("Moderator"),
                    is_verified: card.innerHTML.includes("Verified account"),
                    can_follow: rawText.includes("Follow"),
                    can_add_friend: rawText.includes("Add Friend")
                });
            }

            return results;
        }
        """)

        cleaned = {}

        for member in members:
            url = member.get("url", "").strip()
            name = member.get("name", "").strip().lower()

            if not url:
                continue

            if "/user/" not in url:
                continue

            if FB_NAME and name == FB_NAME:
                print(f"Skipping own profile from extract: {member.get('name')}")
                continue

            if url not in cleaned:
                cleaned[url] = member

        return list(cleaned.values())

    async def scroll_and_process_members(self, page, group: dict, max_scrolls: int = 30):
        seen_urls = set()
        same_count_rounds = 0
        last_seen_count = 0

        bad_name_words = [
            "points",
            "contribution",
            "contributions",
            "badge",
            "badges",
        ]

        bad_url_parts = [
            "/contributions/",
            "/badges/",
            "/posts/",
            "/about/",
            "/friends/",
            "/photos/",
            "/videos/",
        ]

        def is_valid_member_url(url: str) -> bool:
            if not url:
                return False

            if "/groups/" not in url:
                return False

            if "/user/" not in url:
                return False

            for bad_part in bad_url_parts:
                if bad_part in url:
                    return False

            parts = url.rstrip("/").split("/")

            if "groups" not in parts:
                return False

            if "user" not in parts:
                return False

            user_index = parts.index("user")

            # Must end exactly after /user/{id}
            if len(parts) != user_index + 2:
                return False

            user_id = parts[user_index + 1]

            if not user_id:
                return False

            return True

        def is_valid_member_name(name: str) -> bool:
            if not name:
                return False

            lowered = name.lower().strip()

            for word in bad_name_words:
                if word in lowered:
                    return False

            if lowered.isdigit():
                return False

            return True

        for i in range(max_scrolls):
            visible_members = await self.extract_visible_members(page)
            new_members = []

            for member in visible_members:
                url = member.get("url", "").strip()
                name = member.get("name", "").strip()

                if not is_valid_member_url(url):
                    print(f"Skipping invalid member URL: {url}")
                    continue

                if not is_valid_member_name(name):
                    print(f"Skipping invalid member name: {name} | {url}")
                    continue

                if url in seen_urls:
                    continue

                seen_urls.add(url)
                new_members.append(member)

            for member in new_members:
                member_name = member.get("name", "").strip().lower()

                if FB_NAME and member_name == FB_NAME:
                    print(f"Skipping own profile: {member['name']}")
                    continue

                if SKIP_ADMINS and member.get("is_admin"):
                    print(f"Skipping admin: {member['name']}")
                    continue

                if SKIP_MODERATORS and member.get("is_moderator"):
                    print(f"Skipping moderator: {member['name']}")
                    continue

                if SKIP_VERIFIED and member.get("is_verified"):
                    print(f"Skipping verified member: {member['name']}")
                    continue

                saved = await save_group_member(group, member)

                print("-" * 80)
                print(f"Group: {group['name']}")
                print(f"Saved: {saved}")
                print(f"Name: {member['name']}")
                print(f"URL: {member['url']}")
                print(f"Admin: {member['is_admin']}")
                print(f"Moderator: {member['is_moderator']}")
                print(f"Verified: {member['is_verified']}")

                already_messaged = await has_member_been_messaged(member["url"])

                if already_messaged:
                    print(f"Already messaged/drafted. Skipping: {member['name']}")
                    continue

                profile_page = await self.open_member_profile_tab(member)

                if not profile_page:
                    continue

                try:
                    print(f"Ready to scrape profile: {profile_page.url}")

                    await self.type_message_to_member(profile_page, member)

                finally:
                    await profile_page.close()

                await self.cooldown(
                    page,
                    "after member",
                    MEMBER_COOLDOWN_MIN,
                    MEMBER_COOLDOWN_MAX,
                )

            print(
                f"Members scroll {i + 1}: new={len(new_members)} total={len(seen_urls)}"
            )

            if len(seen_urls) == last_seen_count:
                same_count_rounds += 1
            else:
                same_count_rounds = 0

            if same_count_rounds >= 4:
                print("No new members found. Stopping member scroll.")
                break

            last_seen_count = len(seen_urls)

            await page.mouse.wheel(0, 2500)

            await self.cooldown(
                page,
                "members scroll",
                SCROLL_COOLDOWN_MIN,
                SCROLL_COOLDOWN_MAX,
            )

        return list(seen_urls)

    async def open_member_profile_tab(self, member: dict):
        profile_page = await self.page.context.new_page()

        try:
            await profile_page.goto(
                member["url"],
                wait_until="domcontentloaded",
            )

            await profile_page.wait_for_timeout(4000)

            if "/user/" not in profile_page.url:
                print(f"Not a member profile: {profile_page.url}")
                await profile_page.close()
                return None

            print(f"Opened profile tab: {member['name']}")

            await self.cooldown(
                profile_page,
                "after opening profile",
                PROFILE_COOLDOWN_MIN,
                PROFILE_COOLDOWN_MAX,
            )

            return profile_page

        except Exception as e:
            print(f"Failed opening profile tab for {member.get('name')}: {e}")
            await profile_page.close()
            return None

    async def open_message_box(self, profile_page, member: dict):
        try:
            message_button = profile_page.locator(
                'div[role="button"][aria-label="Message"]'
            ).first

            await message_button.wait_for(timeout=10000)
            await message_button.scroll_into_view_if_needed()
            await message_button.click()

            print("Clicked Message button")

            textbox = profile_page.locator(
                'div[role="textbox"][contenteditable="true"][aria-placeholder="Aa"][aria-label^="Write to"]'
            ).last

            await textbox.wait_for(timeout=15000)
            await textbox.click()

            aria_label = await textbox.get_attribute("aria-label")

            print(f"Message composer opened: {aria_label}")

            return textbox

        except Exception as e:
            print(f"Failed opening message box: {e}")
            return None

    def load_random_message(self, member: dict):
        path = Path("messages.json")

        if not path.exists():
            print("messages.json not found")
            return None

        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        messages = data.get("messages", [])
        settings = data.get("settings", {})

        if not messages:
            return None

        selected = random.choice(messages)
        text = selected.get("text", "")

        if settings.get("use_placeholders", True):
            text = text.replace("{{name}}", member.get("name", ""))

        return text

    async def type_message_to_member(self, profile_page, member: dict):
        already_messaged = await has_member_been_messaged(member["url"])

        if already_messaged:
            print(f"Skipping already messaged member: {member['name']}")
            return False

        message_text = self.load_random_message(member)

        if not message_text:
            print("No message found in messages.json")
            return False

       
        textbox = await self.open_message_box(profile_page, member)

        if not textbox:
            return False

        await textbox.click()

        await textbox.press_sequentially(
            message_text,
            delay=35,
        )

        print(f"Typed message to {member['name']}: {message_text}")

        await mark_member_message_drafted(member, message_text)

        await profile_page.wait_for_timeout(200)

        send_button = profile_page.locator(
            '[aria-label="Press enter to send"]'
        )


        await send_button.wait_for(timeout=10000)
        await send_button.click()

        print(f"Sent message to {member['name']}")

        await mark_member_message_sent(
            member,
            message_text,
        )

        return True

    async def join_group_from_link(self, group: dict):
        url = group["url"]

        group_page = await self.page.context.new_page()

        try:
            await group_page.goto(url, wait_until="domcontentloaded")
            await group_page.wait_for_timeout(5000)

            join_button = group_page.locator(
                "div[role='button'][aria-label='Join group']"
            ).first

            if await join_button.count() == 0:
                print(f"No Join group button found: {group['name']}")
                await update_group_status(url, "no_join_button")
                return False

            await join_button.wait_for(timeout=10000)
            await join_button.click()

            print(f"Clicked Join group: {group['name']}")

            await group_page.wait_for_timeout(5000)

            await self.handle_participant_questions(group_page)

            await mark_group_joined(url)

            return True

        except Exception as e:
            print(f"Failed joining {group['name']}: {e}")
            await update_group_status(url, "join_failed")
            return False

        finally:
            await group_page.close()

    async def get_answer_for_question(self, question: str) -> str:
        q = question.lower()

        if "מקום מגור" in question or "איפה" in question or "where" in q:
            return "אני גר באזור."

        if "מטרה" in question or "why" in q or "למה" in question:
            return "אני רוצה להצטרף כדי לקבל מידע רלוונטי ולעזור כשאפשר."

        if "כמה אהבה" in question or "1 עד 10" in question:
            return "10"

        if "עשר פחות חמש" in question:
            return "5"

        if "ישראלי" in question or "ישראל" in question:
            return "כן"

        print("No rule matched. Calling AI...")
        print(f"AI question: {question}")

        answer = await ask_ai_for_group_answer(question)

        print(f"AI returned: {answer}")

        return answer

    async def handle_participant_questions(self, page) -> bool:
        dialog = page.locator("div[role='dialog']").first

        try:
            await dialog.wait_for(timeout=8000)
            print("Join dialog found.")
        except Exception:
            print("No join dialog found.")
            return False

        async def scroll_dialog_down():
            await dialog.evaluate("""
            dialog => {
                const scrollable =
                    Array.from(dialog.querySelectorAll("*"))
                        .find(el => el.scrollHeight > el.clientHeight + 80) ||
                    dialog;

                scrollable.scrollTop += 700;
            }
            """)
            await page.wait_for_timeout(900)

        async def get_question_for_textarea(textarea):
            return await textarea.evaluate("""
            textarea => {
                const block =
                    textarea.closest("[data-visualcompletion='ignore-dynamic']") ||
                    textarea.closest("label")?.parentElement?.parentElement?.parentElement;

                return (
                    block?.innerText ||
                    textarea.getAttribute("aria-label") ||
                    ""
                ).trim();
            }
            """)

        async def get_answer_for_checkbox_question(question: str, options: list[str]) -> str | None:
            joined_options = " ".join(options).lower()

            print("Checkbox question:")
            print(question)
            print("Options:", options)

            if "עשר פחות חמש" in question:
                return "5"

            if "נגד חרם" in question or "חרם על ילדים" in question:
                for option in options:
                    if "ברור" in option or "מה השאלה" in option or "כן" in option:
                        return option

            if "כן" in joined_options:
                for option in options:
                    if "כן" in option:
                        return option

            print("No checkbox rule matched. Calling AI...")
            answer = await self.get_answer_for_question(
                f"Question: {question}\nOptions: {options}\nReturn exactly one option."
            )

            print(f"AI checkbox answer returned: {answer}")

            for option in options:
                if answer.strip() in option or option.strip() in answer:
                    return option

            return None

        seen_textareas = set()
        seen_checkbox_questions = set()

        for round_index in range(8):
            print(f"Dialog pass {round_index + 1}")

            textareas = dialog.locator("textarea")

            for i in range(await textareas.count()):
                textarea = textareas.nth(i)

                textarea_id = await textarea.get_attribute("id")

                if textarea_id and textarea_id in seen_textareas:
                    continue

                question = await get_question_for_textarea(textarea)

                if (
                    not question
                    or question.strip().lower() == "write an answer..."
                ):
                    question = await textarea.get_attribute("aria-label") or ""

                if (
                    not question
                    or question.strip().lower() == "write an answer..."
                ):
                    print("Could not determine textarea question. Skipping.")
                    continue

                seen_textareas.add(textarea_id or question)

                print("-" * 80)
                print(f"Text question found: {question}")

                answer = await self.get_answer_for_question(question)

                print(f"Answer used: {answer}")

                await textarea.scroll_into_view_if_needed()
                await textarea.fill(answer)
                await page.wait_for_timeout(700)

            question_blocks = dialog.locator("[data-visualcompletion='ignore-dynamic']")

            for i in range(await question_blocks.count()):
                block = question_blocks.nth(i)

                checkboxes = block.locator("input[type='checkbox']")

                if await checkboxes.count() == 0:
                    continue

                block_text = (await block.inner_text()).strip()

                if not block_text:
                    continue

                if block_text in seen_checkbox_questions:
                    continue

                labels = block.locator("label")
                options = []

                for j in range(await labels.count()):
                    label_text = (await labels.nth(j).inner_text()).strip()

                    if label_text:
                        options.append(label_text)

                if not options:
                    continue

                seen_checkbox_questions.add(block_text)

                if (
                    "I agree to the group rules" in block_text
                    or "group rules" in block_text.lower()
                    or "תנאי הקבוצה" in block_text
                    or "אני מסכים" in block_text
                ):
                    for j in range(await labels.count()):
                        label = labels.nth(j)
                        text = (await label.inner_text()).strip()

                        if (
                            "agree" in text.lower()
                            or "rules" in text.lower()
                            or "תנאי" in text
                            or "מסכים" in text
                        ):
                            await label.scroll_into_view_if_needed()
                            await label.click(force=True)
                            print("Clicked group rules checkbox.")
                            await page.wait_for_timeout(700)

                    continue

                selected_option = await get_answer_for_checkbox_question(
                    block_text,
                    options,
                )

                if selected_option:
                    for j in range(await labels.count()):
                        label = labels.nth(j)
                        text = (await label.inner_text()).strip()

                        if text == selected_option:
                            await label.scroll_into_view_if_needed()
                            await label.click(force=True)
                            print(f"Clicked checkbox option: {selected_option}")
                            await page.wait_for_timeout(700)
                            break
                else:
                    print("Could not decide checkbox option. Skipping.")

            await scroll_dialog_down()

        await dialog.evaluate("""
        dialog => {
            const scrollable =
                Array.from(dialog.querySelectorAll("*"))
                    .find(el => el.scrollHeight > el.clientHeight + 80) ||
                dialog;

            scrollable.scrollTop = scrollable.scrollHeight;
        }
        """)

        await page.wait_for_timeout(1500)

        submit = dialog.locator("div[role='button'][aria-label='Submit']").last

        try:
            await submit.wait_for(timeout=8000)

            disabled = await submit.get_attribute("aria-disabled")

            if disabled == "true":
                print("Submit button is still disabled. Some required answers may be missing.")
                return False

            await submit.click(force=True)
            print("Submitted participant questions.")

            await page.wait_for_timeout(4000)
            return True

        except Exception as e:
            print(f"Could not submit participant questions: {e}")
            return False