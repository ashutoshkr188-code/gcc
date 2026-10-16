"""Phase 8/9: render every page in a real browser at desktop and phone widths.

Checks: page loads without console errors, the main heading renders, key content is
present, and there is no horizontal page scroll. Screenshots go to $UI_SCREENSHOT_DIR if set.
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

pw = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent
CHROMIUM = next(iter(sorted(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux/chrome"))), None)

PAGES = [
    ("overview", "India GCC research, backed by evidence", "Sources retrieved"),
    ("explorer", "GCC Explorer", "result(s)"),
    ("compare", "City Comparison", "No cost chart is shown"),
    ("groups", "Company Groups", "No group structures documented yet"),
    ("policies", "Policies & Incentives", "Maharashtra GCC Policy 2025"),
    ("evidence", "Evidence & Verification", "Data Quality Center"),
    ("assistant", "Research Assistant", "Ask a question"),
]
VIEWPORTS = {"desktop": (1280, 900), "phone": (390, 844)}


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    db = tmp_path_factory.mktemp("ui") / "ui.sqlite"
    env = {**os.environ, "GCC_ATLAS_DB": str(db), "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}
    subprocess.run([sys.executable, "-m", "gcc_atlas.cli", "--db", str(db), "seed"], cwd=ROOT, env=env, check=True,
                   capture_output=True)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "gcc_atlas.api:app", "--port", str(port)],
                            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            if requests.get(base + "/api/health", timeout=1, proxies={"http": None}).ok:
                break
        except requests.RequestException:
            time.sleep(0.2)
    yield base
    proc.terminate()
    proc.wait()


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        kw = {"executable_path": str(CHROMIUM)} if CHROMIUM else {}
        b = p.chromium.launch(**kw)
        yield b
        b.close()


@pytest.mark.parametrize("vp", list(VIEWPORTS))
@pytest.mark.parametrize("page_id,heading,expect", PAGES)
def test_page_renders(server, browser, vp, page_id, heading, expect):
    w, h = VIEWPORTS[vp]
    ctx = browser.new_context(viewport={"width": w, "height": h})
    page = ctx.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{server}/#/{page_id}")
    page.wait_for_function("() => !document.querySelector('#main').textContent.includes('Loading')")
    page.wait_for_selector(f"text={expect}", timeout=5000)
    assert page.locator("main h1").first.inner_text() == heading
    assert page.locator(".rail a.active").inner_text().replace("&", "&") .strip() != ""
    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    assert overflow <= 0, f"horizontal page scroll of {overflow}px"
    shots = os.environ.get("UI_SCREENSHOT_DIR")
    if shots:
        page.screenshot(path=f"{shots}/{page_id}-{vp}.png", full_page=True)
    assert not errors, errors
    ctx.close()


def test_explorer_filter_and_company_drawer(server, browser):
    page = browser.new_page()
    page.goto(f"{server}/#/explorer")
    page.wait_for_selector("text=result(s)")
    page.click("button.chip[data-city='Gurugram']")
    page.wait_for_selector("text=1 result(s)")
    page.click("tr[data-company='american-express']")
    page.wait_for_selector("#drawer:not([hidden]) >> text=India centres")
    assert "Gurugram" in page.inner_text("#drawer-body")
    page.click("#drawer-body details summary")
    page.click("#drawer-body button[data-claim]")
    page.wait_for_selector("text=Evidence record #")
    assert "Blocked by network" in page.inner_text("#drawer-body")
    page.keyboard.press("Escape")
    assert page.is_hidden("#drawer")
    page.close()


def test_top_search_goes_to_explorer(server, browser):
    page = browser.new_page()
    page.goto(f"{server}/#/overview")
    page.wait_for_selector("text=Sources retrieved")
    page.fill("#topsearch-input", "Lilly")
    page.press("#topsearch-input", "Enter")
    page.wait_for_selector("text=2 result(s)")
    assert page.locator("tbody tr").count() == 2
    page.close()


def test_assistant_answers_with_citations(server, browser):
    page = browser.new_page()
    page.goto(f"{server}/#/assistant")
    page.click("button[data-ex='Which companies have GCCs in Pune?']")
    page.wait_for_selector("text=Records found")
    links = page.locator("#ra-out a[href^='https://']")
    assert links.count() >= 2
    page.close()


def test_compare_city_toggle(server, browser):
    page = browser.new_page()
    page.goto(f"{server}/#/compare")
    page.wait_for_selector("text=No cost chart is shown")
    page.click("button[data-c='Noida']")
    page.wait_for_function("() => document.querySelectorAll('#cmp .cols .card').length === 3")
    assert "cities=Bengaluru%2CHyderabad%2CNoida" in page.url
    page.close()
