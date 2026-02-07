from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import re

from .db import ClaimStore


@dataclass
class RewardEvent:
    source: str
    reward_type: str
    amount_sc: float
    status: str
    details: str


class CasinoCollector:
    """MVP-safe collector simulation.

    Real automation should be added per-casino and comply with terms/captcha policies.
    """

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


class EmailPromoParser:
    def __init__(self, store: ClaimStore) -> None:
        self.store = store

    def parse_email_text(self, sender: str, subject: str, body: str) -> list[RewardEvent]:
        text = f"{subject}\n{body}"
        events: list[RewardEvent] = []

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

    def run_daily(self) -> list[RewardEvent]:
        return self.collector.run_daily_collection()

    def ingest_email(self, sender: str, subject: str, body: str) -> list[RewardEvent]:
        return self.parser.parse_email_text(sender, subject, body)

    def recent_claims(self) -> Iterable:
        return self.store.list_claims()

    def dashboard_totals(self) -> dict[str, float]:
        return self.store.totals()
