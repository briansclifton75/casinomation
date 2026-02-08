from __future__ import annotations

import os
from dataclasses import asdict, dataclass


@dataclass
class ClaimRunResult:
    casino: str
    status: str
    details: str
    screenshot_path: str | None = None


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def run_claim(casino: str, promo_url: str, dry_run: bool = True) -> ClaimRunResult:
    casino_key = casino.lower().strip()
    if casino_key != "chumba":
        return ClaimRunResult(casino, "failed", f"Unsupported casino adapter: {casino}")

    user = _env("CASINOMATION_CHUMBA_USER")
    password = _env("CASINOMATION_CHUMBA_PASSWORD")
    if not user or not password:
        return ClaimRunResult(
            casino,
            "failed",
            "Missing credentials: CASINOMATION_CHUMBA_USER/CASINOMATION_CHUMBA_PASSWORD",
        )

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover
        return ClaimRunResult(casino, "failed", f"Playwright unavailable: {exc}")

    screenshot_path = f"artifacts/{casino_key}-claim.png"
    os.makedirs("artifacts", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Step 1: login page
        page.goto("https://lobby.chumbacasino.com/", wait_until="domcontentloaded", timeout=45000)

        # Step 2: dry-run stops before side effects
        if dry_run:
            page.screenshot(path=screenshot_path, full_page=True)
            browser.close()
            return ClaimRunResult(
                casino,
                "manual_required",
                "Dry run complete. Login + claim steps not executed.",
                screenshot_path=screenshot_path,
            )

        # Step 3: attempt login and open promo link
        page.fill('input[type="email"]', user)
        page.fill('input[type="password"]', password)
        page.click('button:has-text("Log In")')
        page.wait_for_timeout(3000)

        page.goto(promo_url, wait_until="domcontentloaded", timeout=45000)

        # NOTE: selector is intentionally conservative and may need per-promo tuning
        if page.locator('button:has-text("Claim")').count() > 0:
            page.locator('button:has-text("Claim")').first.click()
            page.wait_for_timeout(2500)
            status = "claimed"
            details = "Claim button clicked"
        else:
            status = "manual_required"
            details = "No claim button found; captcha/2FA or selector update needed"

        page.screenshot(path=screenshot_path, full_page=True)
        browser.close()
        return ClaimRunResult(casino, status, details, screenshot_path=screenshot_path)


def run_claim_dict(casino: str, promo_url: str, dry_run: bool = True) -> dict:
    return asdict(run_claim(casino=casino, promo_url=promo_url, dry_run=dry_run))
