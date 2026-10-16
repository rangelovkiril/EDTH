"""Run against the running demo server; saves desktop and mobile screenshots."""

from pathlib import Path

from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parent.parent
with sync_playwright() as p:
    browser = p.chromium.launch(channel="chromium", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1100}, device_scale_factor=1)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto("http://127.0.0.1:8000")
    page.wait_for_function("document.querySelector('#camera-count').textContent === '2 / 2'")
    page.wait_for_function(
        "[...document.querySelectorAll('.camera img')].every(img => img.naturalWidth > 0)"
    )
    page.screenshot(path=str(root / "docs/dashboard-desktop.png"), full_page=True)
    page.locator("#threshold").fill("28")
    page.get_by_role("button", name="Apply settings").click()
    page.wait_for_function(
        "async () => (await (await fetch('/api/state')).json()).settings.threshold === 28"
    )
    page.locator("#mask-toggle").check()
    page.wait_for_timeout(500)
    page.locator("#mask-toggle").uncheck()
    page.locator("#threshold").fill("20")
    page.get_by_role("button", name="Apply settings").click()
    page.wait_for_function(
        "async () => (await (await fetch('/api/state')).json()).settings.threshold === 20"
    )
    page.get_by_role("button", name="Reset background").click()
    page.wait_for_function(
        "document.querySelector('#toast').textContent.startsWith('Background reset')"
    )
    with page.expect_download() as download:
        page.get_by_role("link", name="Export events").click()
    assert download.value.suggested_filename == "skywatch-events.csv"
    canvas = page.locator("#space").bounding_box()
    page.mouse.move(canvas["x"] + 100, canvas["y"] + 100)
    page.mouse.down()
    page.mouse.move(canvas["x"] + 160, canvas["y"] + 120)
    page.mouse.up()
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(300)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path=str(root / "docs/dashboard-mobile.png"), full_page=True)
    # Simulate loss of the API. Previously drawn data must be labeled stale.
    page.route("**/api/state", lambda route: route.abort())
    page.wait_for_function("document.querySelector('#connection').textContent.includes('OFFLINE')")
    assert "stale" in page.locator("#notice").inner_text()
    assert not errors, errors
    browser.close()
    print(
        "Browser checks passed: frames, settings, mask, reset, CSV, orbit,"
        " mobile width, stale state, no JS errors."
    )
