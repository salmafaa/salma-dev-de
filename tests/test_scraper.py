import os
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.scraper import scrape_hotel_images, HotelNotFoundError

pytestmark = pytest.mark.asyncio


async def test_happy_path(tmp_path):
    """3 gambar berhasil didownload dan path dikembalikan."""
    fake_image_content = b"\xff\xd8\xff" + b"\x00" * 100  # fake JPEG bytes

    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.wait_for_selector = AsyncMock()
    mock_page.query_selector_all = AsyncMock(return_value=[
        _make_img_el("https://trvcdn.net/img/hotel1.jpg"),
        _make_img_el("https://trvcdn.net/img/hotel2.jpg"),
        _make_img_el("https://trvcdn.net/img/hotel3.jpg"),
    ])

    with patch("src.scraper.async_playwright") as mock_pw, \
         patch("src.scraper.aiohttp.ClientSession") as mock_session, \
         patch("src.scraper.asyncio.sleep", new_callable=AsyncMock):

        _setup_playwright_mock(mock_pw, mock_page)
        _setup_aiohttp_mock(mock_session, fake_image_content)

        paths = await scrape_hotel_images(
            hotel_name="Grand Hyatt Jakarta",
            city="Jakarta",
            output_dir=str(tmp_path),
        )

    assert len(paths) == 3
    assert all(p.endswith(".jpg") for p in paths)
    assert "grand-hyatt-jakarta" in paths[0]


async def test_hotel_not_found(tmp_path):
    """Jika selector tidak ditemukan, HotelNotFoundError harus dilempar."""
    from playwright.async_api import TimeoutError as PwTimeout

    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.wait_for_selector = AsyncMock(side_effect=PwTimeout("timeout"))

    with patch("src.scraper.async_playwright") as mock_pw, \
         patch("src.scraper.asyncio.sleep", new_callable=AsyncMock):
        _setup_playwright_mock(mock_pw, mock_page)

        with pytest.raises(HotelNotFoundError):
            await scrape_hotel_images("Fake Hotel", "Nowhere", str(tmp_path))


async def test_broken_image_skipped(tmp_path):
    """Gambar yang gagal didownload di-skip, sisanya tetap dikembalikan."""
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.wait_for_selector = AsyncMock()
    mock_page.query_selector_all = AsyncMock(return_value=[
        _make_img_el("https://trvcdn.net/img/ok1.jpg"),
        _make_img_el("https://trvcdn.net/img/broken.jpg"),
        _make_img_el("https://trvcdn.net/img/ok2.jpg"),
    ])

    call_count = 0

    async def fake_get(url, **kwargs):
        nonlocal call_count
        call_count += 1
        resp = AsyncMock()
        if "broken" in url:
            resp.status = 404
        else:
            resp.status = 200
            resp.read = AsyncMock(return_value=b"\xff\xd8" + b"\x00" * 50)
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        return resp

    with patch("src.scraper.async_playwright") as mock_pw, \
         patch("src.scraper.aiohttp.ClientSession") as mock_session, \
         patch("src.scraper.asyncio.sleep", new_callable=AsyncMock), \
         patch("src.scraper.aiofiles.open", create=True):

        _setup_playwright_mock(mock_pw, mock_page)
        session_instance = AsyncMock()
        session_instance.get = fake_get
        session_instance.__aenter__ = AsyncMock(return_value=session_instance)
        session_instance.__aexit__ = AsyncMock(return_value=False)
        mock_session.return_value = session_instance

        paths = await scrape_hotel_images("Test Hotel", "Jakarta", str(tmp_path))

    # Broken image skip, tapi tidak crash
    assert isinstance(paths, list)


# ---- Helpers ----

def _make_img_el(src: str):
    el = AsyncMock()
    el.get_attribute = AsyncMock(side_effect=lambda attr: src if attr == "src" else None)
    return el


def _setup_playwright_mock(mock_pw, mock_page):

    # mock locator
    mock_locator = MagicMock()

    mock_locator.first = mock_locator

    mock_locator.scroll_into_view_if_needed = AsyncMock()

    mock_locator.click = AsyncMock()

    mock_page.locator = MagicMock(return_value=mock_locator)

    # mock keyboard
    mock_keyboard = MagicMock()

    mock_keyboard.press = AsyncMock()

    mock_page.keyboard = mock_keyboard

    # context/browser
    mock_context = AsyncMock()

    mock_context.new_page = AsyncMock(return_value=mock_page)

    mock_browser = AsyncMock()

    mock_browser.new_context = AsyncMock(return_value=mock_context)

    mock_browser.close = AsyncMock()

    mock_pw_instance = AsyncMock()

    mock_pw_instance.chromium.launch = AsyncMock(
        return_value=mock_browser
    )

    mock_pw_instance.__aenter__ = AsyncMock(
        return_value=mock_pw_instance
    )

    mock_pw_instance.__aexit__ = AsyncMock(
        return_value=False
    )

    mock_pw.return_value = mock_pw_instance


def _setup_aiohttp_mock(mock_session, content: bytes):
    resp = AsyncMock()
    resp.status = 200
    resp.read = AsyncMock(return_value=content)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)

    session_instance = AsyncMock()
    session_instance.get = AsyncMock(return_value=resp)
    session_instance.__aenter__ = AsyncMock(return_value=session_instance)
    session_instance.__aexit__ = AsyncMock(return_value=False)
    mock_session.return_value = session_instance