from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse
import os
import re

from .db import ClaimStore
from .email_ingest import GmailPromoIngestor


CASINO_HINTS = {
    "chumba": ("chumba", "chumbacasino.com"),
    "modo": ("modo", "modo.us"),
    "fortunecoins": ("fortune coins", "fortunecoins"),
    "hardrock": ("hard rock", "hardrock"),
    "yay": ("yaycasino", "yaycasino.com"),
    "luckyland": ("luckyland",),
    "globalpoker": ("global poker", "globalpoker"),
}


@dataclass
class RewardEvent:
    source: str
    reward_type: str
    amount_sc: float
    status: str
    details: str
    claim_url: str = ""
    casino: str = "unknown"


class CasinoCollector:
    def __init__(self, store: ClaimStore) -> None:
        self.store = store

    def run_daily_collection(self) -> list[RewardEvent]:
        events = [
            RewardEvent("Lucky River", "daily_sc", 1.00, "claimed", "Daily bonus collected."),
            RewardEvent(
                "Gold Spin Club",
                "daily_sc",
                0.50,
                "manual_required",
                "Captcha required before claim.",
            ),
            RewardEvent("Star Vault", "daily_sc", 0.75, "claimed", "Daily login reward."),
        ]
        for event in events:
            self.store.add_claim(**event.__dict__)
        return events


PROMO_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?P<amount>\d+(?:\.\d+)?)\s*SC", re.IGNORECASE),
    re.compile(r"(?P<spins>\d+)\s*free\s*spins?", re.IGNORECASE),
)

FREE_GIFT_HINTS = (
    "free spins",
    "free spin",
    "free coins",
    "free sc",
    "daily bonus",
    "claim now",
    "no purchase necessary",
    "gift",
    "reward",
)

DEPOSIT_REQUIRED_HINTS = (
    "deposit required",
    "minimum deposit",
    "min deposit",
    "with purchase",
    "buy coins",
    "purchase required",
    "first purchase",
    "top up",
    "welcome back offer",
    "40% off",
    "50% off",
    "% off",
)


def _detect_casino(sender: str, claim_url: str) -> str:
    blob = f"{sender} {claim_url}".lower()
    for casino, hints in CASINO_HINTS.items():
        if any(h in blob for h in hints):
            return casino
    return "unknown"


def _is_valid_claim_url(url: str) -> bool:
    if not url:
        return False
    if any(x in url.lower() for x in ("schema.org", "sendgrid", "fonts.googleapis", "w3.org")):
        return False
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.netloc.lower()
    return any(h in host for h in ("casino", "chumba", "modo", "fortunecoins", "luckyland", "globalpoker", "hardrock", "yay"))


def _is_no_deposit_gift_email(subject: str, body: str) -> bool:
    text = f"{subject}\n{body}".lower()
    has_free_signal = any(h in text for h in FREE_GIFT_HINTS)
    has_deposit_signal = any(h in text for h in DEPOSIT_REQUIRED_HINTS)
    return has_free_signal and not has_deposit_signal


class EmailPromoParser:
    def __init__(self, store: ClaimStore) -> None:
        self.store = store

    def parse_email_text(self, sender: str, subject: str, body: str, claim_url: str = "") -> list[RewardEvent]:
        text = f"{subject}\n{body}"
        events: list[RewardEvent] = []
        casino = _detect_casino(sender, claim_url)

        if casino == "unknown" or not _is_valid_claim_url(claim_url):
            return []

        if not _is_no_deposit_gift_email(subject, body):
            return []

        for pattern in PROMO_PATTERNS:
            for match in pattern.finditer(text):
                if "amount" in match.groupdict() and match.group("amount"):
                    amount = float(match.group("amount"))
                    events.append(
                        RewardEvent(
                            source=sender,
                            reward_type="email_sc",
                            amount_sc=amount,
                            status="manual_required",
                            details="Promo SC found in email; open source link to claim.",
                            claim_url=claim_url,
                            casino=casino,
                        )
                    )
                if "spins" in match.groupdict() and match.group("spins"):
                    spins = int(match.group("spins"))
                    events.append(
                        RewardEvent(
                            source=sender,
                            reward_type="free_spin",
                            amount_sc=0,
                            status="manual_required",
                            details=f"{spins} free spins found in email promo.",
                            claim_url=claim_url,
                            casino=casino,
                        )
                    )

        if not events:
            events.append(
                RewardEvent(
                    source=sender,
                    reward_type="promo_link",
                    amount_sc=0,
                    status="manual_required",
                    details="Promo link detected; amount not parsed yet.",
                    claim_url=claim_url,
                    casino=casino,
                )
            )

        for event in events:
            self.store.add_claim(**event.__dict__)
        return events


class RewardService:
    def __init__(self, store: ClaimStore) -> None:
        self.store = store
        self.collector = CasinoCollector(store)
        self.parser = EmailPromoParser(store)
        self.imap = GmailPromoIngestor()
        self.enable_dummy_collector = os.getenv("CASINOMATION_ENABLE_DUMMY_COLLECTOR", "false").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def run_daily(self) -> list[RewardEvent]:
        if not self.enable_dummy_collector:
            return []
        return self.collector.run_daily_collection()

    def ingest_email(self, sender: str, subject: str, body: str, claim_url: str = "") -> list[RewardEvent]:
        return self.parser.parse_email_text(sender, subject, body, claim_url=claim_url)

    def recent_claims(self) -> Iterable:
        return self.store.list_claims()

    def dashboard_totals(self) -> dict[str, float]:
        return self.store.totals()

    def scan_email_inbox(self, max_messages: int = 20) -> dict[str, int]:
        scanned = 0
        new_messages = 0
        new_events = 0
        filtered_deposit_required = 0

        for msg in self.imap.fetch_recent(max_messages=max_messages):
            scanned += 1
            message_id = msg["message_id"]
            if self.store.already_ingested(message_id):
                continue

            if not _is_no_deposit_gift_email(msg["subject"], msg["body"]):
                filtered_deposit_required += 1
                self.store.mark_ingested(message_id, msg["sender"], msg["subject"])
                continue

            events = self.ingest_email(
                msg["sender"],
                msg["subject"],
                msg["body"],
                claim_url=msg.get("claim_url", ""),
            )
            self.store.mark_ingested(message_id, msg["sender"], msg["subject"])
            new_messages += 1
            new_events += len(events)

        return {
            "scanned": scanned,
            "new_messages": new_messages,
            "new_events": new_events,
            "filtered_deposit_required": filtered_deposit_required,
        }

    def pending_promos(self, limit: int = 50) -> list[dict]:
        return [c.__dict__ for c in self.store.list_pending_promos(limit=limit)]
