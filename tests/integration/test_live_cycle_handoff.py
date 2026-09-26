import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


class LiveCycleHandoffTests(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.temp_directory = (
            tempfile.TemporaryDirectory()
        )

        self.temp_root = Path(
            self.temp_directory.name
        )

        self.repo_root = (
            Path(__file__)
            .resolve()
            .parents[2]
        )

        self.live_dir = (
            self.temp_root
            / "repo"
            / "codex"
            / "trading-live"
        )

        self.live_dir.mkdir(
            parents=True
        )

        self.script = (
            self.live_dir
            / "run_live_cycle.sh"
        )

        shutil.copy2(
            (
                self.repo_root
                / "codex"
                / "trading-live"
                / "run_live_cycle.sh"
            ),
            self.script,
        )

        # Codex fake only needs a prompt file to exist.
        (
            self.live_dir
            / "LIVE_RUN.md"
        ).write_text(
            "test live prompt\n",
            encoding="utf-8",
        )

        # The production script derives REPO_ROOT
        # from RUN_DIR and adds REPO_ROOT/src to
        # PYTHONPATH. The fake Python executable
        # means the directory does not need code,
        # but keeping it present mirrors production.
        (
            self.temp_root
            / "repo"
            / "src"
        ).mkdir()

        self.fake_bin = (
            self.temp_root
            / "fake-bin"
        )
        self.fake_bin.mkdir()

        self.codex_marker = (
            self.temp_root
            / "codex-called.txt"
        )

        self._write_fake_commands()

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def _write_executable(
        self,
        name: str,
        body: str,
    ) -> None:
        path = (
            self.fake_bin
            / name
        )

        path.write_text(
            body,
            encoding="utf-8",
        )

        path.chmod(
            path.stat().st_mode
            | stat.S_IXUSR
        )

    def _write_fake_commands(
        self,
    ) -> None:
        self._write_executable(
            "date",
            """#!/bin/zsh
case "$1" in
  "+%u")
    print -r -- "${FAKE_WEEKDAY:-3}"
    ;;
  "+%H%M")
    print -r -- "${FAKE_TIME_ET:-1200}"
    ;;
  *)
    /bin/date "$@"
    ;;
esac
""",
        )

        self._write_executable(
            "python",
            """#!/bin/zsh
print -r -- "${FAKE_EQUITY_RESULT:-EQUITY ENTRY CYCLE RESULT: NO ACTION}"
exit "${FAKE_PYTHON_EXIT:-0}"
""",
        )

        self._write_executable(
            "codex",
            """#!/bin/zsh
print -r -- "called" >> "$FAKE_CODEX_MARKER"
print -r -- "${FAKE_CODEX_RESULT:-LIVE CYCLE RESULT: NO ACTION}"
exit "${FAKE_CODEX_EXIT:-0}"
""",
        )

    def _arm(self) -> None:
        (
            self.live_dir
            / "ARM_ONCE"
        ).write_text(
            "armed\n",
            encoding="utf-8",
        )

    def _run(
        self,
        **overrides: str,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()

        env.update(
            {
                "PATH": (
                    f"{self.fake_bin}:"
                    f"{env['PATH']}"
                ),
                "FAKE_CODEX_MARKER": str(
                    self.codex_marker
                ),

                # These are intentionally fake.
                # The fake Python executable never
                # connects to Robinhood.
                "ROBINHOOD_ACCOUNT_NUMBER":
                    "test-account",
                "ROBINHOOD_NOT_FOUND_GRACE_SECONDS":
                    "120",
                "STOCK_AGENT_RUNTIME_MODE":
                    "live",
                "ROBINHOOD_LIVE_EXECUTION_ENABLED":
                    "true",
            }
        )

        env.update(
            overrides
        )

        return subprocess.run(
            [
                "/bin/zsh",
                str(self.script),
            ],
            cwd=self.live_dir,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_equity_submission_stops_before_codex(
        self,
    ) -> None:
        self._arm()

        result = self._run(
            FAKE_EQUITY_RESULT=(
                "EQUITY ENTRY CYCLE RESULT: "
                "OPENING ORDER SUBMITTED"
            )
        )

        self.assertEqual(
            result.returncode,
            0,
            msg=result.stderr,
        )

        self.assertFalse(
            self.codex_marker.exists()
        )

        self.assertFalse(
            (
                self.live_dir
                / "ARM_ONCE"
            ).exists()
        )

        self.assertIn(
            (
                "EQUITY ENTRY CYCLE RESULT: "
                "OPENING ORDER SUBMITTED"
            ),
            result.stdout,
        )

    def test_no_equity_action_allows_codex_phase(
        self,
    ) -> None:
        self._arm()

        result = self._run(
            FAKE_EQUITY_RESULT=(
                "EQUITY ENTRY CYCLE RESULT: "
                "NO ACTION"
            )
        )

        self.assertEqual(
            result.returncode,
            0,
            msg=result.stderr,
        )

        self.assertTrue(
            self.codex_marker.exists()
        )

        self.assertEqual(
            self.codex_marker
            .read_text(
                encoding="utf-8"
            )
            .splitlines(),
            [
                "called",
            ],
        )

        self.assertFalse(
            (
                self.live_dir
                / "ARM_ONCE"
            ).exists()
        )

    def test_equity_runtime_failure_blocks_codex(
        self,
    ) -> None:
        self._arm()

        result = self._run(
            FAKE_PYTHON_EXIT="1",
        )

        self.assertNotEqual(
            result.returncode,
            0,
        )

        self.assertFalse(
            self.codex_marker.exists()
        )

        self.assertFalse(
            (
                self.live_dir
                / "ARM_ONCE"
            ).exists()
        )

        self.assertIn(
            "failed safely",
            result.stdout.lower(),
        )

    def test_review_only_result_fails_closed(
        self,
    ) -> None:
        self._arm()

        result = self._run(
            FAKE_EQUITY_RESULT=(
                "EQUITY ENTRY CYCLE RESULT: "
                "REVIEW ONLY"
            )
        )

        self.assertNotEqual(
            result.returncode,
            0,
        )

        self.assertFalse(
            self.codex_marker.exists()
        )

        self.assertFalse(
            (
                self.live_dir
                / "ARM_ONCE"
            ).exists()
        )

    def test_unknown_equity_result_fails_closed(
        self,
    ) -> None:
        self._arm()

        result = self._run(
            FAKE_EQUITY_RESULT=(
                "unexpected result"
            )
        )

        self.assertNotEqual(
            result.returncode,
            0,
        )

        self.assertFalse(
            self.codex_marker.exists()
        )

    def test_missing_arm_blocks_everything(
        self,
    ) -> None:
        result = self._run()

        self.assertNotEqual(
            result.returncode,
            0,
        )

        self.assertFalse(
            self.codex_marker.exists()
        )

        self.assertIn(
            "Not armed",
            result.stdout,
        )

    def test_stop_file_blocks_before_consuming_arm(
        self,
    ) -> None:
        self._arm()

        (
            self.live_dir
            / "STOP"
        ).write_text(
            "stop\n",
            encoding="utf-8",
        )

        result = self._run()

        self.assertNotEqual(
            result.returncode,
            0,
        )

        self.assertFalse(
            self.codex_marker.exists()
        )

        # STOP happens before authorization is
        # consumed.
        self.assertTrue(
            (
                self.live_dir
                / "ARM_ONCE"
            ).exists()
        )

    def test_codex_prompt_forbids_all_equity_execution(
        self,
    ) -> None:
        raw_prompt = (
            self.repo_root
            / "codex"
            / "trading-live"
            / "LIVE_RUN.md"
        ).read_text(
            encoding="utf-8"
        )

        prompt = " ".join(
            raw_prompt.split()
        )

        self.assertIn(
            (
                "The production Python runtime "
                "exclusively owns all equity execution."
            ),
            prompt,
        )

        self.assertIn(
            (
                "Codex has zero equity "
                "execution authority."
            ),
            prompt,
        )

        self.assertIn(
            "place an equity BUY",
            prompt,
        )

        self.assertIn(
            "place an equity SELL",
            prompt,
        )

        self.assertIn(
            (
                "Codex execution authority "
                "is OPTIONS ONLY."
            ),
            prompt,
        )

        self.assertNotIn(
            (
                "For equities, permit only:"
            ),
            prompt,
        )

        self.assertNotIn(
            (
                "sell + close of currently "
                "owned shares"
            ),
            prompt,
        )

    def test_workspace_policy_forbids_all_codex_equity_execution(
        self,
    ) -> None:
        raw_policy = (
            self.repo_root
            / "codex"
            / "trading-live"
            / "AGENTS.override.md"
        ).read_text(
            encoding="utf-8"
        )

        policy = " ".join(
            raw_policy.split()
        )

        self.assertIn(
            (
                "All equity execution is exclusively "
                "owned by the production Python runtime"
            ),
            policy,
        )

        self.assertIn(
            (
                "Codex has zero equity "
                "execution authority."
            ),
            policy,
        )

        self.assertIn(
            (
                "Never submit an equity "
                "buy/opening order."
            ),
            policy,
        )

        self.assertIn(
            (
                "Never submit an equity "
                "sell/closing order."
            ),
            policy,
        )

        self.assertIn(
            (
                "Codex execution authority "
                "is options only."
            ),
            policy,
        )

        self.assertNotIn(
            (
                "Equity sells are permitted"
            ),
            policy,
        )

        self.assertNotIn(
            (
                "equity closing: sell only "
                "currently owned shares"
            ),
            policy,
        )

        self.assertNotIn(
            "buy eligible stock",
            policy.lower(),
        )

    def test_equity_closing_submission_stops_before_codex(
        self,
    ) -> None:
        self._arm()

        result = self._run(
            FAKE_EQUITY_RESULT=(
                "EQUITY ENTRY CYCLE RESULT: "
                "CLOSING ORDER SUBMITTED"
            )
        )

        self.assertEqual(
            result.returncode,
            0,
            msg=result.stderr,
        )

        self.assertFalse(
            self.codex_marker.exists()
        )

        self.assertFalse(
            (
                self.live_dir
                / "ARM_ONCE"
            ).exists()
        )

        self.assertIn(
            (
                "EQUITY ENTRY CYCLE RESULT: "
                "CLOSING ORDER SUBMITTED"
            ),
            result.stdout,
        )      


if __name__ == "__main__":
    unittest.main()