from __future__ import annotations

import os
from dataclasses import asdict, dataclass


@dataclass
class ClaimRunResult:
    casino: str
    status: str
    details: str
    screenshot_path: str | None = None


ADAPTERS = {
    "chumba": {
        "login_url": "https://lobby.chumbacasino.com/",
        "user_env": "CASINOMATION_CHUMBA_USER",
        "pass_env": "CASINOMATION_CHUMBA_PASSWORD",
        "user_selector": 'input[type="email"]',
        "pass_selector": 'input[type="password"]',
        "login_button": 'button:has-text("Log In")',
        "claim_selector": 'button:has-text("Claim")',
    },
    "modo": {
        "login_url": "https://modo.us/lobby",
        "user_env": "CASINOMATION_MODO_USER",
        "pass_env": "CASINOMATION_MODO_PASSWORD",
        "user_selector": 'input[type="email"]',
        "pass_selector": 'input[type="password"]',
        "login_button": 'button:has-text("Log In")',
        "claim_selector": 'button:has-text("Claim")',
    },
    "fortunecoins": {
        "login_url": "https://www.fortunecoins.com/",
        "user_env": "CASINOMATION_FORTUNE_USER",
        "pass_env": "CASINOMATION_FORTUNE_PASSWORD",
        "user_selector": 'input[type="email"]',
        "pass_selector": 'input[type="password"]',
        "login_button": 'button:has-text("Log In")',
        "claim_selector": 'button:has-text("Claim")',
    },
}


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def run_claim(casino: str, promo_url: str, dry_run: bool = True) -> ClaimRunResult:
    casino_key = casino.lower().strip()
    cfg = ADAPTERS.get(casino_key)
    if not cfg:
        return ClaimRunResult(casino, "failed", f"Unsupported casino adapter: {casino}")

    user = _env(cfg["user_env"])
    password = _env(cfg["pass_env"])
    if not user or not password:
        return ClaimRunResult(casino, "failed", f"Missing credentials: {cfg['user_env']}/{cfg['pass_env']}")

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

        page.goto(cfg["login_url"], wait_until="domcontentloaded", timeout=45000)

        if dry_run:
            page.screenshot(path=screenshot_path, full_page=True)
            browser.close()
            return ClaimRunResult(casino, "manual_required", "Dry run complete. Login + claim steps not executed.", screenshot_path)

        try:
            page.fill(cfg["user_selector"], user)
            page.fill(cfg["pass_selector"], password)
            page.click(cfg["login_button"])
            page.wait_for_timeout(3500)
        except Exception:
            page.screenshot(path=screenshot_path, full_page=True)
            browser.close()
            return ClaimRunResult(casino, "manual_required", "Login selectors failed or MFA/captcha gate hit", screenshot_path)

        page.goto(promo_url, wait_until="domcontentloaded", timeout=45000)

        if page.locator(cfg["claim_selector"]).count() > 0:
            page.locator(cfg["claim_selector"]).first.click()
            page.wait_for_timeout(2500)
            status = "claimed"
            details = "Claim button clicked"
        else:
            status = "manual_required"
            details = "No claim button found; captcha/2FA or selector tuning needed"

        page.screenshot(path=screenshot_path, full_page=True)
        browser.close()
        return ClaimRunResult(casino, status, details, screenshot_path)


def run_claim_dict(casino: str, promo_url: str, dry_run: bool = True) -> dict:
    return asdict(run_claim(casino=casino, promo_url=promo_url, dry_run=dry_run))
