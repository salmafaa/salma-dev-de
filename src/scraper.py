# src/scraper.py

import asyncio
import os
from pathlib import Path

import aiofiles
import aiohttp
from playwright.async_api import (
    TimeoutError as PwTimeout,
)
from playwright.async_api import async_playwright
from slugify import slugify

REQUEST_DELAY = 2  # seconds


class HotelNotFoundError(Exception):
    """Raised when no hotel matching the query is found on Traveloka."""


# =========================================================
# DOWNLOAD IMAGE
# =========================================================
async def _download_image(
    session: aiohttp.ClientSession,
    url: str,
    dest_path: str,
) -> bool:
    """Download a single image."""

    try:

        resp = await session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=15),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            },
        )

        if resp.status != 200:
            return False

        content = await resp.read()

        async with aiofiles.open(dest_path, "wb") as f:
            await f.write(content)

        return True

    except Exception as e:

        print(f"Download error: {e}")

        return False


# =========================================================
# MAIN SCRAPER
# =========================================================
async def scrape_hotel_images(
    hotel_name: str,
    city: str,
    output_dir: str,
    max_images: int = 3,
) -> list[str]:

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    slug = slugify(hotel_name)

    image_urls: list[str] = []

    async with async_playwright() as pw:

        browser = await pw.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-ID",
            viewport={"width": 1280, "height": 800},
            java_script_enabled=True,
        )

        # hide automation
        await context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            })
            """
        )

        page = await context.new_page()

        # =========================================================
        # OPEN TRAVELOKA
        # =========================================================

        try:

            await page.goto(
                "https://www.traveloka.com/en-id/hotel",
                timeout=60000,
                wait_until="domcontentloaded",
            )

        except PwTimeout:

            await browser.close()

            raise HotelNotFoundError(
                f"Traveloka timeout for '{hotel_name}'"
            )

        await asyncio.sleep(5)

        # =========================================================
        # INPUT SEARCH
        # =========================================================

        try:

            print("Cari search input...")

            search_input = await page.wait_for_selector(
                "input[placeholder*='City'], "
                "input[placeholder*='Hotel'], "
                "input[placeholder*='Destination'], "
                "input[placeholder*='Search']",
                timeout=20000,
            )

            await search_input.click()

            await asyncio.sleep(1)

            await search_input.fill(f"{hotel_name} {city}")

            print("Berhasil isi search")

        except Exception as e:

            await browser.close()

            raise HotelNotFoundError(
                f"Search input gagal: {e}"
            )

        await asyncio.sleep(3)

        # =========================================================
        # CLICK CITY SUGGESTION
        # =========================================================

        try:

            print("Klik dropdown kota...")

            await page.wait_for_selector(
                "[data-testid^='accom_autocomplete_item_']",
                timeout=15000,
            )

            suggestion = page.locator(
                f"[data-testid^='accom_autocomplete_item_']:has-text('{city}')"
            ).first

            await suggestion.scroll_into_view_if_needed()

            await suggestion.click(force=True)

            print("Dropdown berhasil diklik")

        except Exception as e:

            print(f"Dropdown gagal: {e}")

            print("Fallback pakai keyboard...")

            try:
                await page.keyboard.press("ArrowDown")
                await asyncio.sleep(1)
                await page.keyboard.press("Enter")

            except Exception as kb_error:
                print(f"Keyboard fallback gagal: {kb_error}")

        await asyncio.sleep(3)

        # =========================================================
        # CLICK SEARCH BUTTON
        # =========================================================

        try:

            print("Klik tombol search...")

            search_btn = page.locator(
                "[data-testid='search-submit-button']"
            )

            await search_btn.scroll_into_view_if_needed()

            await search_btn.click(force=True)

            print("Search berhasil diklik")

        except Exception as e:

            print(f"Search button gagal: {e}")

            print("Fallback tekan Enter...")

            try:
                await page.keyboard.press("Enter")

            except Exception as kb_error:
                print(f"Keyboard enter gagal: {kb_error}")

        # =========================================================
        # WAIT RESULTS
        # =========================================================

        await asyncio.sleep(REQUEST_DELAY)

        try:

            print("Menunggu hasil hotel muncul...")

            await page.wait_for_selector(
                "[data-testid='list-view-card-main-image']",
                timeout=20000,
            )

            print("Hasil hotel muncul")

        except PwTimeout:

            await browser.close()

            raise HotelNotFoundError(
                f"No hotel results found for '{hotel_name}' in '{city}'"
            )

        # =========================================================
        # GET IMAGE URLS
        # =========================================================

        img_elements = await page.query_selector_all(
            "[data-testid='list-view-card-main-image']"
        )

        print(f"Jumlah image ditemukan: {len(img_elements)}")

        for el in img_elements:

            src = (
                await el.get_attribute("src")
                or await el.get_attribute("data-src")
            )

            if not src:
                continue

            # resolve relative URL
            if src.startswith("//"):
                src = "https:" + src

            elif src.startswith("/"):
                src = "https://www.traveloka.com" + src

            if src not in image_urls:
                image_urls.append(src)

            if len(image_urls) >= max_images:
                break

        await browser.close()

    # =========================================================
    # VALIDATE IMAGES
    # =========================================================

    if not image_urls:

        raise HotelNotFoundError(
            f"No images found for '{hotel_name}' in '{city}'"
        )

    # =========================================================
    # DOWNLOAD IMAGES
    # =========================================================

    saved_paths: list[str] = []

    async with aiohttp.ClientSession() as session:

        for n, url in enumerate(image_urls[:max_images], start=1):

            await asyncio.sleep(REQUEST_DELAY)

            dest = os.path.join(
                output_dir,
                f"{slug}_{n}.jpg",
            )

            success = await _download_image(
                session=session,
                url=url,
                dest_path=dest,
            )

            if success:

                saved_paths.append(dest)

                print(f"Downloaded: {dest}")

            else:

                print(f"Gagal download: {url}")

    return saved_paths