from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "casinomation.db"
DB_PATH = Path(os.getenv("CASINOMATION_DB", str(DEFAULT_DB_PATH))).expanduser()


@dataclass
class Claim:
    id: int
    source: str
    reward_type: str
    amount_sc: float
    status: str
    details: str
    claimed_at: str


class ClaimStore:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS claims (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    reward_type TEXT NOT NULL,
                    amount_sc REAL NOT NULL,
                    status TEXT NOT NULL,
                    details TEXT NOT NULL,
                    claimed_at TEXT NOT NULL
                )
                """
            )

    def add_claim(
        self,
        source: str,
        reward_type: str,
        amount_sc: float,
        status: str,
        details: str,
    ) -> int:
        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO claims (source, reward_type, amount_sc, status, details, claimed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (source, reward_type, amount_sc, status, details, now),
            )
            return int(cursor.lastrowid)

    def list_claims(self, limit: int = 50) -> Iterable[Claim]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM claims ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [Claim(**dict(row)) for row in rows]

    def totals(self) -> dict[str, float]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN status = 'claimed' THEN amount_sc ELSE 0 END), 0) as total_sc,
                    COALESCE(SUM(CASE WHEN reward_type = 'free_spin' THEN 1 ELSE 0 END), 0) as free_spins,
                    COALESCE(SUM(CASE WHEN status = 'claimed' THEN 1 ELSE 0 END), 0) as successful_claims,
                    COALESCE(SUM(CASE WHEN status != 'claimed' THEN 1 ELSE 0 END), 0) as unresolved
                FROM claims
                """
            ).fetchone()
        return {
            "total_sc": float(row["total_sc"]),
            "free_spins": float(row["free_spins"]),
            "successful_claims": float(row["successful_claims"]),
            "unresolved": float(row["unresolved"]),
        }
