from config import FB_EMAIL, FB_PASSWORD


async def is_logged_in(page) -> bool:
    await page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)

    url = page.url.lower()

    if "login" in url:
        return False

    try:
        await page.locator("[aria-label='Facebook']").first.wait_for(timeout=5000)
        return True
    except Exception:
        return "facebook.com" in url and "login" not in url


async def login(page):
    if await is_logged_in(page):
        print("Already logged in.")
        return

    print("Logging in automatically...")

    await page.goto("https://www.facebook.com/login", wait_until="domcontentloaded")

    await page.fill("input[name='email']", FB_EMAIL)
    await page.fill("input[name='pass']", FB_PASSWORD)

    await page.click("button[name='login']")

    await page.wait_for_timeout(8000)

    url = page.url.lower()

    if "checkpoint" in url or "two_step_verification" in url:
        print("Facebook needs manual verification / 2FA.")
        input("Finish it in the browser, then press ENTER...")

    if await is_logged_in(page):
        print("Login successful.")
    else:
        raise RuntimeError("Login failed. Check credentials or Facebook checkpoint.")