from pathlib import Path
import tempfile
import unittest
import os

from casinomation.db import ClaimStore
from casinomation.services import EmailPromoParser, RewardService


class ServicesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "test.db"
        self.store = ClaimStore(db_path)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_email_parser_finds_sc_and_spins(self) -> None:
        parser = EmailPromoParser(self.store)
        events = parser.parse_email_text(
            "promo@test.com",
            "Claim 5 SC + 25 free spins",
            "Use link now for 1.5 SC bonus",
        )
        self.assertEqual(len(events), 3)
        totals = self.store.totals()
        self.assertEqual(totals["free_spins"], 1.0)

    def test_daily_collector_records_claims(self) -> None:
        os.environ["CASINOMATION_ENABLE_DUMMY_COLLECTOR"] = "true"
        service = RewardService(self.store)
        events = service.run_daily()
        self.assertEqual(len(events), 3)
        claims = list(service.recent_claims())
        self.assertEqual(len(claims), 3)
        os.environ["CASINOMATION_ENABLE_DUMMY_COLLECTOR"] = "false"


if __name__ == "__main__":
    unittest.main()
