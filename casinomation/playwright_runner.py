from __future__ import annotations

import imaplib
import email
import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from pathlib import Path


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
        "google_button": 'button:has-text("Google"), a:has-text("Google")',
    },
    "modo": {
        "login_url": "https://modo.us/lobby",
        "user_env": "CASINOMATION_MODO_USER",
        "pass_env": "CASINOMATION_MODO_PASSWORD",
        "user_selector": 'input[type="email"]',
        "pass_selector": 'input[type="password"]',
        "login_button": 'button:has-text("Log In")',
        "claim_selector": 'button:has-text("Claim")',
        "google_button": 'button:has-text("Google"), a:has-text("Google")',
    },
    "fortunecoins": {
        "login_url": "https://www.fortunecoins.com/",
        "user_env": "CASINOMATION_FORTUNE_USER",
        "pass_env": "CASINOMATION_FORTUNE_PASSWORD",
        "user_selector": 'input[type="email"]',
        "pass_selector": 'input[type="password"]',
        "login_button": 'button:has-text("Log In")',
        "claim_selector": 'button:has-text("Claim")',
        "google_button": 'button:has-text("Google"), a:has-text("Google")',
    },
}


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _decode_mime(value: str | None) -> str:
    if not value:
        return ""
    out: list[str] = []
    for chunk, charset in decode_header(value):
        if isinstance(chunk, bytes):
            out.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(chunk)
    return "".join(out)


def _latest_google_otp(timeout_sec: int = 90) -> str | None:
    user = _env("CASINOMATION_IMAP_USER")
    password = _env("CASINOMATION_IMAP_APP_PASSWORD")
    host = _env("CASINOMATION_IMAP_HOST") or "imap.gmail.com"
    port = int(_env("CASINOMATION_IMAP_PORT") or "993")
    if not user or not password:
        return None

    sender_filter = (_env("CASINOMATION_GOOGLE_OTP_SENDER") or "google").lower()
    end = time.time() + timeout_sec
    seen: set[str] = set()

    while time.time() < end:
        try:
            with imaplib.IMAP4_SSL(host, port) as mail:
                mail.login(user, password)
                mail.select("INBOX")
                since = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%d-%b-%Y")
                status, data = mail.search(None, "SINCE", since)
                if status != "OK" or not data or not data[0]:
                    time.sleep(5)
                    continue

                ids = [x for x in data[0].split() if x][-20:]
                for msg_id in reversed(ids):
                    res, msg_data = mail.fetch(msg_id, "(RFC822)")
                    if res != "OK" or not msg_data or not msg_data[0]:
                        continue
                    msg = email.message_from_bytes(msg_data[0][1])
                    from_h = _decode_mime(msg.get("From")).lower()
                    if sender_filter not in from_h:
                        continue
                    mid = _decode_mime(msg.get("Message-ID")) or msg_id.decode()
                    if mid in seen:
                        continue
                    seen.add(mid)
                    subject = _decode_mime(msg.get("Subject"))
                    text = subject
                    payload = msg.get_payload(decode=True)
                    if payload:
                        text += "\n" + payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
                    m = re.search(r"\b(\d{6})\b", text)
                    if m:
                        return m.group(1)
        except Exception:
            pass
        time.sleep(5)
    return None


def _is_logged_in(page, cfg: dict) -> bool:
    try:
        if page.locator(cfg["user_selector"]).count() > 0:
            return False
        return True
    except Exception:
        return False


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
    sessions_dir = Path("artifacts/sessions")
    sessions_dir.mkdir(parents=True, exist_ok=True)
    storage_state = sessions_dir / f"{casino_key}.json"

    headless = _env("CASINOMATION_BROWSER_HEADLESS").lower() not in {"0", "false", "no"}
    google_auth = _env(f"CASINOMATION_{casino_key.upper()}_GOOGLE_AUTH").lower() in {"1", "true", "yes", "on"}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=str(storage_state)) if storage_state.exists() else browser.new_context()
        page = context.new_page()

        page.goto(cfg["login_url"], wait_until="domcontentloaded", timeout=45000)

        if dry_run:
            page.screenshot(path=screenshot_path, full_page=True)
            context.storage_state(path=str(storage_state))
            browser.close()
            return ClaimRunResult(casino, "manual_required", "Dry run complete. Login + claim steps not executed.", screenshot_path)

        if not _is_logged_in(page, cfg):
            try:
                if google_auth and page.locator(cfg["google_button"]).count() > 0:
                    page.locator(cfg["google_button"]).first.click()
                    page.wait_for_timeout(2000)
                    otp = _latest_google_otp(timeout_sec=120)
                    if otp:
                        if page.locator('input[type="tel"], input[autocomplete="one-time-code"], input[type="text"]').count() > 0:
                            page.locator('input[type="tel"], input[autocomplete="one-time-code"], input[type="text"]').first.fill(otp)
                            page.keyboard.press("Enter")
                            page.wait_for_timeout(3000)
                        else:
                            page.screenshot(path=screenshot_path, full_page=True)
                            browser.close()
                            return ClaimRunResult(casino, "manual_required", "Google OTP field not found", screenshot_path)
                    else:
                        page.screenshot(path=screenshot_path, full_page=True)
                        browser.close()
                        return ClaimRunResult(casino, "manual_required", "Google OTP not found in inbox", screenshot_path)
                else:
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
        context.storage_state(path=str(storage_state))
        browser.close()
        return ClaimRunResult(casino, status, details, screenshot_path)


def run_claim_dict(casino: str, promo_url: str, dry_run: bool = True) -> dict:
    return asdict(run_claim(casino=casino, promo_url=promo_url, dry_run=dry_run))
