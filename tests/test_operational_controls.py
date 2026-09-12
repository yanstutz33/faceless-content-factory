import tempfile
import threading
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from factory.operational_controls import (
    CrossWorkspaceClaims,
    CrossWorkspaceDuplicateError,
    OperationalLimitError,
    UsageLedger,
    UsagePolicy,
    credential_expiry_summary,
    operational_health,
)


class OperationalControlsTests(unittest.TestCase):
    def test_worker_reserves_waiting_jobs_without_consuming_active_slots(self):
        from factory.web import JobRunner
        with tempfile.TemporaryDirectory() as directory:
            ledger = UsageLedger(Path(directory) / "usage.sqlite3", UsagePolicy(max_active=1, max_queue=4))
            started, release = threading.Event(), threading.Event()

            class FakePipeline:
                def run(self, job_id):
                    started.set()
                    release.wait(timeout=5)

            runner = JobRunner(FakePipeline(), workers=1, usage=ledger, workspace_id="alpha")
            try:
                runner.submit("first")
                self.assertTrue(started.wait(timeout=2))
                runner.submit("second")
                states = ledger.snapshot("alpha")["states"]
                self.assertEqual(states["active"], 1)
                self.assertEqual(states["reserved"], 1)
            finally:
                release.set()
                runner.executor.shutdown(wait=True)

    def test_limits_queue_attempts_and_daily_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = UsageLedger(Path(directory) / "usage.json",
                                 UsagePolicy(max_active=1, max_queue=2, max_attempts=2,
                                             max_metric_syncs_per_day=1))
            ledger.reserve("render-a", "alpha")
            ledger.start("render-a")
            ledger.reserve("render-b", "beta")
            with self.assertRaises(OperationalLimitError):
                ledger.start("render-b")
            ledger.attempt("render-a")
            ledger.attempt("render-a")
            with self.assertRaises(OperationalLimitError):
                ledger.attempt("render-a")
            ledger.finish("render-a", "failed", error="simulated")
            ledger.reserve("metrics-a", "alpha", kind="metrics")
            ledger.finish("metrics-a")
            with self.assertRaises(OperationalLimitError):
                ledger.reserve("metrics-b", "alpha", kind="metrics")

    def test_cross_workspace_publication_claim_is_rejected_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            claims = CrossWorkspaceClaims(Path(directory) / "claims.json")
            first = claims.claim("alpha", "youtube", "sha256:video", "job-a")
            again = claims.claim("alpha", "youtube", "sha256:video", "job-a")
            self.assertFalse(first["idempotent"])
            self.assertTrue(again["idempotent"])
            with self.assertRaises(CrossWorkspaceDuplicateError):
                claims.claim("beta", "youtube", "sha256:video", "job-b")
            with self.assertRaises(CrossWorkspaceDuplicateError):
                claims.claim("alpha", "youtube", "sha256:video", "job-c")

    def test_cross_process_style_claims_are_transactional(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "claims.sqlite3"
            ledgers = [CrossWorkspaceClaims(path), CrossWorkspaceClaims(path)]
            barrier = threading.Barrier(2)
            results = []

            def claim(index):
                barrier.wait()
                try:
                    ledgers[index].claim(f"workspace-{index}", "youtube", "same-video", f"job-{index}")
                    results.append("accepted")
                except CrossWorkspaceDuplicateError:
                    results.append("blocked")

            threads = [threading.Thread(target=claim, args=(index,)) for index in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertCountEqual(results, ["accepted", "blocked"])

    def test_retry_budget_survives_a_new_ledger_instance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "usage.sqlite3"
            policy = UsagePolicy(max_attempts=2)
            first = UsageLedger(path, policy)
            first.reserve("render-a", "alpha")
            first.attempt("render-a")
            first.finish("render-a", "failed")
            second = UsageLedger(path, policy)
            second.reserve("render-a", "alpha")
            second.attempt("render-a")
            second.finish("render-a", "failed")
            with self.assertRaises(OperationalLimitError):
                second.reserve("render-a", "alpha")
                second.attempt("render-a")

    def test_recovery_only_releases_selected_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "usage.sqlite3"
            ledger = UsageLedger(path, UsagePolicy(max_active=2, max_queue=4))
            for workspace in ("alpha", "beta"):
                operation = f"render-{workspace}"
                ledger.reserve(operation, workspace)
                ledger.start(operation)
            self.assertEqual(ledger.recover_interrupted("alpha"), 1)
            self.assertEqual(ledger.snapshot("alpha")["states"]["cancelled"], 1)
            self.assertEqual(ledger.snapshot("beta")["states"]["active"], 1)

    def test_health_report_redacts_credentials_and_reports_expiry(self):
        with tempfile.TemporaryDirectory() as directory:
            now = datetime(2026, 9, 9, tzinfo=UTC)
            usage = UsageLedger(Path(directory) / "usage.json")
            claims = CrossWorkspaceClaims(Path(directory) / "claims.json")
            report = operational_health(usage, claims, [{
                "platform": "youtube", "expires_at": (now + timedelta(days=5)).isoformat(),
                "access_token": "must-not-appear",
            }], now=now)
            self.assertEqual(report["credentials"][0]["state"], "expiring_soon")
            self.assertNotIn("must-not-appear", str(report))
            self.assertFalse(report["cost_signals"]["publishing_performed"])

    def test_expiry_summary_handles_expired_invalid_and_unknown(self):
        now = datetime(2026, 9, 9, tzinfo=UTC)
        result = credential_expiry_summary([
            {"platform": "a", "expires_at": "2026-09-08T00:00:00Z"},
            {"platform": "b", "expires_at": "not-a-date"},
            {"platform": "c"},
        ], now=now)
        self.assertEqual([item["state"] for item in result], ["expired", "invalid", "unknown"])


if __name__ == "__main__":
    unittest.main()
