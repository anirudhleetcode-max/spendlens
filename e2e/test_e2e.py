"""Full user journey through the real UI (headless Chromium) against running backend + frontend.

Run via ./run_e2e.sh (starts both servers), or with servers already up:
    BASE_URL=http://127.0.0.1:5174 python -m pytest e2e/test_e2e.py -v
"""
from __future__ import annotations

import os
import random
import sys
import uuid
from datetime import date
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from ml.receipts_synth import SHOPS, make_receipt, render  # noqa: E402

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:5174")
SHOTS = ROOT / "docs" / "screenshots"
EXTRA_SHOTS = Path(os.environ["EXTRA_SHOTS"]) if os.environ.get("EXTRA_SHOTS") else None


def inr(v: float) -> str:
    """Indian grouping like the UI: 1,23,456.00"""
    whole, frac = f"{v:.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:]); head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"₹{whole}.{frac}"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True, locale="en-IN")
    pg = ctx.new_page()
    pg.set_default_timeout(15_000)
    yield pg
    ctx.close()


@pytest.fixture(scope="module")
def receipt(tmp_path_factory):
    rng = random.Random(2024)
    lines, truth = make_receipt(rng, SHOPS[0], on=date.today())  # DMart, dated today
    path = tmp_path_factory.mktemp("rc") / "dmart_bill.jpg"
    render(lines, rng).save(path, "JPEG", quality=88)
    return path, truth


def shot(page: Page, name: str, full: bool = False):
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / name), full_page=full)


def test_full_journey(page: Page, receipt):
    path, truth = receipt
    email = f"e2e-{uuid.uuid4().hex[:8]}@example.com"

    # --- register
    page.goto(f"{BASE}/login")
    expect(page.get_by_role("heading", name="Sign in")).to_be_visible()
    page.get_by_role("button", name="New here? Create an account").click()
    page.get_by_label("Your name").fill("Meera Iyer")
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password").fill("secret123")
    page.get_by_role("button", name="Create account").click()
    expect(page.get_by_role("heading", name="Scan a receipt")).to_be_visible()

    # --- upload a generated receipt, fields are pre-filled
    page.get_by_test_id("file-input").set_input_files(str(path))
    review = page.get_by_test_id("review")
    expect(review).to_be_visible(timeout=60_000)
    expect(page.locator("#scan-merchant")).to_have_value(truth.merchant)
    assert abs(float(page.locator("#scan-amount").input_value()) - truth.total) < 0.01
    expect(page.locator("#scan-date")).to_have_value(truth.date)
    expect(page.locator("#scan-category")).to_have_value(truth.category)
    expect(page.get_by_test_id("suggestion")).to_contain_text(f"Suggested {truth.category}")
    expect(review.locator(".items-table tbody tr")).to_have_count(len(truth.items))
    page.mouse.move(0, 0)
    shot(page, "scan-review.png")

    # --- correct the category, save
    page.locator("#scan-category").select_option("Shopping")
    expect(page.get_by_test_id("suggestion")).to_contain_text("you changed it")
    page.get_by_role("button", name="Save expense").click()
    expect(page.get_by_text("Saved to your ledger")).to_be_visible()
    expect(page.get_by_role("status")).to_contain_text("Shopping")

    # --- manual expense, category suggested by the model while typing
    page.get_by_role("navigation").get_by_role("link", name="Expenses").click()
    page.get_by_role("button", name="Add expense").click()
    page.locator("#exp-merchant").fill("Uber")
    page.locator("#exp-amount").fill("320")
    expect(page.locator("#exp-category")).to_have_value("Transport & Fuel")
    page.get_by_role("button", name="Save expense").click()
    rows = page.get_by_test_id("expense-row")
    expect(rows).to_have_count(2)
    expect(page.get_by_test_id("expense-table")).to_contain_text(truth.merchant)
    expect(page.get_by_test_id("expense-table")).to_contain_text("Uber")

    # --- filter works
    page.get_by_label("Category").select_option("Transport & Fuel")
    expect(rows).to_have_count(1)
    expect(rows.first).to_contain_text("Uber")
    page.get_by_label("Category").select_option("")
    page.get_by_placeholder("Search merchant, item or note").fill("dmart")
    expect(rows).to_have_count(1)
    expect(rows.first).to_contain_text(truth.merchant)
    page.get_by_role("button", name="Clear filters").click()
    expect(rows).to_have_count(2)

    # --- receipt image viewer
    page.get_by_role("button", name=f"View receipt for {truth.merchant}").click()
    expect(page.locator("dialog.viewer img")).to_be_visible()
    page.keyboard.press("Escape")

    # --- CSV export downloads
    with page.expect_download() as dl:
        page.get_by_role("button", name="Export CSV").click()
    csv_text = Path(dl.value.path()).read_text(encoding="utf-8-sig")
    assert dl.value.suggested_filename.startswith("spendlens-")
    assert "Uber" in csv_text and truth.merchant in csv_text and "Shopping" in csv_text

    # --- budget: Shopping limit below what was spent
    page.get_by_role("navigation").get_by_role("link", name="Budgets").click()
    row = page.get_by_test_id("budget-Shopping")
    row.get_by_label("Budget for Shopping").fill("200")
    row.get_by_role("button", name="Set").click()
    expect(row).to_contain_text("Over budget")
    trow = page.get_by_test_id("budget-Transport & Fuel")
    trow.get_by_label("Budget for Transport & Fuel").fill("50000")
    trow.get_by_role("button", name="Set").click()
    expect(trow).to_contain_text("On track")

    # --- overview adds it all up
    page.get_by_role("navigation").get_by_role("link", name="Overview").click()
    expect(page.get_by_test_id("month-total")).to_have_text(inr(truth.total + 320))
    split = page.get_by_test_id("category-split")
    expect(split).to_contain_text("Shopping")
    expect(split).to_contain_text("Transport & Fuel")
    budgets = page.get_by_test_id("overview-budgets")
    expect(budgets).to_contain_text("Over budget")
    expect(budgets).to_contain_text("On track")
    expect(page.locator("svg[role=img]")).to_be_visible()

    # the correction was learned: the same merchant now defaults to Shopping
    page.get_by_role("navigation").get_by_role("link", name="Expenses").click()
    page.get_by_role("button", name="Add expense").click()
    page.locator("#exp-merchant").fill(truth.merchant)
    expect(page.locator("#exp-category")).to_have_value("Shopping")
    expect(page.get_by_test_id("suggestion")).to_contain_text("Using your earlier choice")


def test_demo_account_screens(page: Page, browser):
    page.goto(f"{BASE}/login")
    page.get_by_role("button", name="Use demo account").click()
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_test_id("month-total")).to_be_visible()
    expect(page.get_by_test_id("anomalies").locator("li").first).to_be_visible()
    page.wait_for_timeout(300)
    shot(page, "overview.png")
    if EXTRA_SHOTS:
        page.screenshot(path=str(EXTRA_SHOTS / "overview-full.png"), full_page=True)

    page.get_by_role("navigation").get_by_role("link", name="Expenses").click()
    expect(page.get_by_test_id("expense-row").first).to_be_visible()
    page.mouse.move(0, 0)
    shot(page, "expenses.png")

    page.get_by_role("navigation").get_by_role("link", name="Budgets").click()
    expect(page.get_by_test_id("budget-table")).to_contain_text("Groceries")
    if EXTRA_SHOTS:
        page.screenshot(path=str(EXTRA_SHOTS / "budgets.png"), full_page=True)
        token = page.evaluate("localStorage.getItem('spendlens.token')")
        ctx = browser.new_context(viewport={"width": 375, "height": 812}, device_scale_factor=2)
        ctx.add_init_script(f"localStorage.setItem('spendlens.token', {token!r})")
        m = ctx.new_page()
        for path, name in [("/", "m-overview"), ("/expenses", "m-expenses"), ("/scan", "m-scan"), ("/budgets", "m-budgets")]:
            m.goto(f"{BASE}{path}")
            m.wait_for_timeout(1200)
            m.screenshot(path=str(EXTRA_SHOTS / f"{name}.png"), full_page=True)
        m.goto(f"{BASE}/login")
        ctx.close()


def test_login_errors(page: Page):
    page.goto(f"{BASE}/login")
    page.get_by_label("Email").fill("nobody@example.com")
    page.get_by_label("Password").fill("wrongpass")
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_role("alert")).to_contain_text("Incorrect email or password")
    if EXTRA_SHOTS:
        page.screenshot(path=str(EXTRA_SHOTS / "login.png"))
