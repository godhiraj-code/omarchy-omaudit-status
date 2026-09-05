import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from scripts import status


SCANNED_AT = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)


def plugin(plugin_id, *, state="unchanged", grade="A", **overrides):
    row = {
        "id": plugin_id,
        "name": plugin_id.title(),
        "version": "1.0.0",
        "dir": f"/home/example/.config/omarchy/plugins/{plugin_id}",
        "kinds": ["bar-widget"],
        "grade": grade,
        "score": 95,
        "observed": [],
        "status": state,
        "firstParty": False,
        "baseline": None,
        "added": ["capability.test"] if state == "changed" else [],
        "composition": [],
        "evidence": {},
    }
    row.update(overrides)
    return row


class BuildStatusTests(unittest.TestCase):
    def test_raw_grade_type_is_validated_before_normalization(self):
        for grade in (None, False, {}, [], ["A"], 0):
            with self.subTest(grade=grade), self.assertRaises(ValueError):
                status.build_status([plugin("wrong-grade", grade=grade)], SCANNED_AT)
        for grade, expected in (("", ""), (" a ", "A")):
            self.assertEqual(status.build_status([plugin("valid", grade=grade)])["worstGrade"], expected)

    def test_clean_and_untracked_results(self):
        document = status.build_status(
            [plugin("clean"), plugin("new", state="not-tracked", grade="")],
            SCANNED_AT,
        )

        self.assertTrue(document["ok"])
        self.assertTrue(document["installed"])
        self.assertEqual(document["scannedAt"], "2026-08-24T12:00:00+00:00")
        self.assertEqual(
            document["totals"],
            {"plugins": 2, "unchanged": 1, "changed": 0,
             "notTracked": 1, "compositionRisks": 0},
        )
        self.assertEqual(document["statusText"], "1 plugin needs baseline")
        self.assertEqual([row["id"] for row in document["plugins"]], ["new", "clean"])
        self.assertEqual(document["worstGrade"], "A")

    def test_changed_and_composition_results_are_bounded(self):
        document = status.build_status(
            [plugin(
                "risky", state="changed", grade="D",
                added=[f"cap-{i}" for i in range(20)],
                composition=[f"reason-{i}" for i in range(10)],
                evidence={f"cap-{i}": ["Panel.qml", i + 1] for i in range(20)},
            )],
            SCANNED_AT,
        )

        self.assertEqual(document["statusText"], "1 plugin changed")
        self.assertEqual(document["worstGrade"], "D")
        self.assertEqual(document["totals"]["compositionRisks"], 1)
        self.assertEqual(len(document["plugins"][0]["added"]), 12)
        self.assertEqual(len(document["plugins"][0]["composition"]), 6)
        self.assertEqual(len(document["plugins"][0]["evidence"]), 12)
        self.assertTrue(set(document["plugins"][0]["evidence"]).issubset(document["plugins"][0]["added"]))

    def test_output_is_limited(self):
        document = status.build_status(
            [plugin(f"p-{i:03}") for i in range(105)],
            SCANNED_AT,
        )

        self.assertEqual(document["totals"]["plugins"], 105)
        self.assertEqual(len(document["plugins"]), 100)

    def test_invalid_row_fails_instead_of_looking_clean(self):
        for bad_row in (None, {}, plugin("", state="changed"), plugin("bad", state="unknown")):
            with self.subTest(row=bad_row), self.assertRaises(ValueError):
                status.build_status([bad_row], SCANNED_AT)

    def test_missing_or_wrong_required_fields_fail_closed(self):
        required_fields = {
            "name": None,
            "version": None,
            "dir": None,
            "kinds": None,
            "grade": None,
            "score": None,
            "observed": None,
            "firstParty": None,
            "baseline": "invalid",
            "added": None,
            "composition": None,
            "evidence": None,
        }
        for field, invalid in required_fields.items():
            row = plugin("partial")
            if invalid is None:
                row.pop(field)
            else:
                row[field] = invalid
            with self.subTest(field=field), self.assertRaises(ValueError):
                status.build_status([row], SCANNED_AT)

        with self.assertRaises(ValueError):
            status.build_status([plugin("bad-first-party", firstParty="yes")], SCANNED_AT)
        with self.assertRaises(ValueError):
            status.build_status([plugin("bad-evidence", evidence={"net.outbound": ["Panel.qml", "9"]})], SCANNED_AT)

    def test_cross_field_contradictions_and_duplicate_ids_fail_closed(self):
        contradictory_rows = [
            plugin("unchanged-added", added=["net.outbound"]),
            plugin("unchanged-evidence", evidence={"net.outbound": ["Panel.qml", 9]}),
            plugin("untracked-added", state="not-tracked", added=["net.outbound"]),
            plugin("changed-empty", state="changed", added=[]),
            plugin(
                "changed-unrelated-evidence",
                state="changed",
                added=["process.exec"],
                evidence={"net.outbound": ["Panel.qml", 9]},
            ),
        ]
        for row in contradictory_rows:
            with self.subTest(plugin=row["id"]), self.assertRaises(ValueError):
                status.build_status([row], SCANNED_AT)

        with self.assertRaisesRegex(ValueError, "duplicate plugin IDs"):
            status.build_status([plugin("same"), plugin("same")], SCANNED_AT)

    def test_totals_and_worst_grade_include_rows_beyond_display_limit(self):
        rows = [plugin(f"p-{index:03}", state="changed") for index in range(100)]
        rows.append(plugin(
            "z-risk",
            grade="F",
            composition=["credentials plus outbound network"],
        ))

        document = status.build_status(rows, SCANNED_AT)

        self.assertEqual(len(document["plugins"]), 100)
        self.assertEqual(document["totals"]["plugins"], 101)
        self.assertEqual(document["totals"]["unchanged"], 1)
        self.assertEqual(document["totals"]["changed"], 100)
        self.assertNotIn("z-risk", [item["id"] for item in document["plugins"]])
        self.assertTrue(all(item["grade"] == "A" for item in document["plugins"]))
        self.assertEqual(document["totals"]["compositionRisks"], 1)
        self.assertEqual(document["worstGrade"], "F")

    def test_absolute_evidence_paths_are_reduced(self):
        document = status.build_status(
            [plugin(
                "safe",
                state="changed",
                added=["network", "unix"],
                evidence={
                    "network": [r"C:\\Users\\alice\\secret\\Panel.qml", 9],
                    "unix": ["/home/alice/plugin/main.py", 12],
                },
            )],
            SCANNED_AT,
        )

        self.assertEqual(document["plugins"][0]["evidence"], {
            "network": {"file": "Panel.qml", "line": 9},
            "unix": {"file": "main.py", "line": 12},
        })

    def test_sorting_grade_coercion_and_field_stripping(self):
        rows = [
            plugin("u-a", state="unchanged", grade="A", directory="/secret", baseline={"x": 1}),
            plugin("n-empty", state="not-tracked", grade=""),
            plugin("c-c", state="changed", grade="C", snippets=["secret"]),
            plugin("c-f", state="changed", grade="F", kinds=["secret"]),
            plugin("n-d", state="not-tracked", grade="D", unknown="secret"),
        ]

        document = status.build_status(rows, SCANNED_AT)

        self.assertEqual(
            [row["id"] for row in document["plugins"]],
            ["c-f", "c-c", "n-d", "n-empty", "u-a"],
        )
        self.assertEqual(document["plugins"][3]["grade"], "")
        allowed = {"id", "name", "version", "grade", "score", "status",
                   "firstParty", "added", "composition", "evidence"}
        self.assertTrue(all(set(row) == allowed for row in document["plugins"]))
        serialized = json.dumps(document)
        for secret_field in ("directory", "baseline", "observed", "snippets", "kinds", "unknown"):
            self.assertNotIn(secret_field, serialized)

    def test_top_level_must_be_a_list(self):
        with self.assertRaises(ValueError):
            status.build_status({"plugins": []}, SCANNED_AT)


class MainTests(unittest.TestCase):
    def run_main(self, completed=None, side_effect=None, argv=None):
        stream = io.StringIO()
        with mock.patch("scripts.status._run_process_bounded", return_value=completed,
                        side_effect=side_effect) as run, \
             mock.patch("sys.argv", argv or ["status.py"]), \
             redirect_stdout(stream):
            result = status.main()
        lines = stream.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        return result, json.loads(lines[0]), run

    def test_missing_executable_is_visible_error(self):
        result, document, _ = self.run_main(side_effect=FileNotFoundError("omaudit"))
        self.assertEqual(result, 0)
        self.assertFalse(document["ok"])
        self.assertFalse(document["installed"])
        self.assertTrue(document["error"])

    def test_timeout_is_visible_error(self):
        result, document, _ = self.run_main(
            side_effect=subprocess.TimeoutExpired(["omaudit"], 120))
        self.assertEqual(result, 0)
        self.assertFalse(document["ok"])
        self.assertTrue(document["installed"])
        self.assertIn("timed out", document["error"].lower())

    def test_malformed_json_is_visible_error(self):
        completed = subprocess.CompletedProcess([], 0, stdout="not json", stderr="")
        _, document, _ = self.run_main(completed)
        self.assertFalse(document["ok"])
        self.assertTrue(document["installed"])
        self.assertIn("json", document["error"].lower())

    def test_unexpected_exit_is_visible_error(self):
        completed = subprocess.CompletedProcess([], 7, stdout="[]", stderr="private detail")
        _, document, _ = self.run_main(completed)
        self.assertFalse(document["ok"])
        self.assertTrue(document["installed"])
        self.assertIn("exit code 7", document["error"].lower())
        self.assertNotIn("private detail", document["error"])

    def test_exit_zero_with_changed_result_is_protocol_error(self):
        completed = subprocess.CompletedProcess(
            [], 0, stdout=json.dumps([plugin("changed", state="changed")]), stderr="")
        _, document, _ = self.run_main(completed)
        self.assertFalse(document["ok"])
        self.assertIn("protocol mismatch", document["error"].lower())

    def test_exit_one_without_changed_result_is_protocol_error(self):
        completed = subprocess.CompletedProcess(
            [], 1, stdout=json.dumps([plugin("clean")]), stderr="")
        _, document, _ = self.run_main(completed)
        self.assertFalse(document["ok"])
        self.assertIn("protocol mismatch", document["error"].lower())

    def test_findings_exit_one_is_accepted_and_default_argv_excludes_builtins(self):
        completed = subprocess.CompletedProcess(
            [], 1, stdout=json.dumps([plugin("changed", state="changed", grade="F")]), stderr="")
        _, document, run = self.run_main(completed)
        self.assertTrue(document["ok"])
        self.assertEqual(document["totals"]["changed"], 1)
        run.assert_called_once_with(
            ["omaudit", "check", "--json"],
            timeout=120,
        )

    def test_include_builtins_adds_all_flag(self):
        completed = subprocess.CompletedProcess([], 0, stdout="[]", stderr="")
        _, document, run = self.run_main(
            completed,
            argv=["status.py", "--include-builtins"],
        )

        self.assertTrue(document["ok"])
        run.assert_called_once_with(
            ["omaudit", "check", "--json", "--all"],
            timeout=120,
        )

    def test_adapter_emits_ascii_safe_json_for_chunked_qml(self):
        completed = subprocess.CompletedProcess(
            [], 0, stdout=json.dumps([plugin("cafe", name="Café")]), stderr="",
        )
        stream = io.StringIO()
        with mock.patch("scripts.status._run_process_bounded", return_value=completed), \
             mock.patch("sys.argv", ["status.py"]), \
             redirect_stdout(stream):
            status.main()

        raw = stream.getvalue()
        self.assertIn(r"Caf\u00e9", raw)
        self.assertNotIn("Café", raw)
        self.assertEqual(json.loads(raw)["plugins"][0]["name"], "Café")

    def test_input_mode_reads_saved_json_without_subprocess(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as saved:
            json.dump([plugin("saved")], saved)
            path = saved.name
        self.addCleanup(Path(path).unlink, missing_ok=True)

        stream = io.StringIO()
        with mock.patch("scripts.status._run_process_bounded") as run, \
             mock.patch("sys.argv", ["status.py", "--input", path]), \
             redirect_stdout(stream):
            result = status.main()

        self.assertEqual(result, 0)
        self.assertEqual(json.loads(stream.getvalue())["totals"]["plugins"], 1)
        run.assert_not_called()

    def test_input_mode_malformed_fixture_is_visible_error(self):
        fixture = Path(__file__).parent / "fixtures" / "malformed.txt"
        stream = io.StringIO()
        with mock.patch("scripts.status._run_process_bounded") as run, \
             mock.patch("sys.argv", ["status.py", "--input", str(fixture)]), \
             redirect_stdout(stream):
            result = status.main()

        document = json.loads(stream.getvalue())
        self.assertEqual(result, 0)
        self.assertFalse(document["ok"])
        self.assertTrue(document["installed"])
        self.assertIn("json", document["error"].lower())
        run.assert_not_called()

    def test_input_mode_rejects_oversized_saved_output(self):
        with tempfile.NamedTemporaryFile("wb", suffix=".json", delete=False) as saved:
            saved.write(b" " * (status.MAX_OMAUDIT_STDOUT_BYTES + 1))
            path = saved.name
        self.addCleanup(Path(path).unlink, missing_ok=True)

        stream = io.StringIO()
        with mock.patch("scripts.status._run_process_bounded") as run, \
             mock.patch("sys.argv", ["status.py", "--input", path]), \
             redirect_stdout(stream):
            result = status.main()

        document = json.loads(stream.getvalue())
        self.assertEqual(result, 0)
        self.assertFalse(document["ok"])
        self.assertIn("size limit", document["error"].lower())
        run.assert_not_called()


class BoundedProcessTests(unittest.TestCase):
    def test_exact_stdout_limit_is_accepted(self):
        command = [
            sys.executable,
            "-c",
            "import sys; sys.stdout.buffer.write(b'x' * 4096)",
        ]

        completed = status._run_process_bounded(
            command, timeout=5, stdout_limit=4096, stderr_limit=1024,
        )

        self.assertEqual(len(completed.stdout), 4096)

    def test_simultaneous_stdout_and_stderr_are_drained(self):
        command = [
            sys.executable,
            "-c",
            "import sys; sys.stdout.buffer.write(b'o' * 4096); "
            "sys.stderr.buffer.write(b'e' * 1024); sys.stdout.flush(); sys.stderr.flush()",
        ]

        completed = status._run_process_bounded(
            command, timeout=5, stdout_limit=4096, stderr_limit=1024,
        )

        self.assertEqual(len(completed.stdout), 4096)
        self.assertEqual(len(completed.stderr), 1024)

    def test_stdout_overflow_terminates_and_fails_closed(self):
        command = [
            sys.executable,
            "-c",
            "import sys,time; sys.stdout.buffer.write(b'x' * 4097); "
            "sys.stdout.flush(); time.sleep(10)",
        ]

        with self.assertRaisesRegex(status.OmauditError, "stdout exceeded"):
            status._run_process_bounded(
                command, timeout=5, stdout_limit=4096, stderr_limit=1024,
            )

    def test_stderr_overflow_terminates_and_fails_closed(self):
        command = [
            sys.executable,
            "-c",
            "import sys,time; sys.stderr.buffer.write(b'x' * 1025); "
            "sys.stderr.flush(); time.sleep(10)",
        ]

        with self.assertRaisesRegex(status.OmauditError, "stderr exceeded"):
            status._run_process_bounded(
                command, timeout=5, stdout_limit=4096, stderr_limit=1024,
            )

    def test_bounded_process_decodes_valid_utf8(self):
        command = [
            sys.executable,
            "-c",
            "import sys; sys.stdout.buffer.write('safe café'.encode())",
        ]

        completed = status._run_process_bounded(
            command, timeout=5, stdout_limit=4096, stderr_limit=1024,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "safe café")

    def test_bounded_process_rejects_invalid_utf8(self):
        command = [
            sys.executable,
            "-c",
            "import sys; sys.stdout.buffer.write(bytes([255]))",
        ]

        with self.assertRaisesRegex(status.OmauditError, "UTF-8"):
            status._run_process_bounded(
                command, timeout=5, stdout_limit=4096, stderr_limit=1024,
            )

    def test_bounded_process_enforces_timeout(self):
        command = [sys.executable, "-c", "import time; time.sleep(10)"]

        with self.assertRaises(subprocess.TimeoutExpired):
            status._run_process_bounded(
                command, timeout=0.1, stdout_limit=4096, stderr_limit=1024,
            )

    @unittest.skipUnless(os.name == "posix", "process-group guarantee is for Omarchy Linux")
    def test_timeout_kills_descendants_that_inherit_pipes(self):
        command = [
            sys.executable,
            "-c",
            "import subprocess,sys,time; "
            "subprocess.Popen([sys.executable,'-c','import time; time.sleep(10)']); "
            "time.sleep(10)",
        ]
        started = time.monotonic()

        with self.assertRaises(subprocess.TimeoutExpired):
            status._run_process_bounded(
                command, timeout=0.1, stdout_limit=4096, stderr_limit=1024,
            )

        self.assertLess(time.monotonic() - started, 4)

    @unittest.skipUnless(os.name == "posix", "direct-parent-exit regression is POSIX-specific")
    def test_timeout_kills_inherited_pipe_descendant_after_parent_exits(self):
        command = [
            sys.executable,
            "-c",
            "import subprocess,sys; "
            "subprocess.Popen([sys.executable,'-c','import time; time.sleep(10)'])",
        ]
        started = time.monotonic()

        with self.assertRaises(subprocess.TimeoutExpired):
            status._run_process_bounded(
                command, timeout=0.1, stdout_limit=4096, stderr_limit=1024,
            )

        self.assertLess(time.monotonic() - started, 4)

    def test_reader_exception_fails_closed(self):
        class BrokenStream:
            def read1(self, _size):
                raise OSError("synthetic read failure")

            def close(self):
                return None

        class EmptyStream:
            def read1(self, _size):
                return b""

            def close(self):
                return None

        class FakeProcess:
            pid = 12345
            returncode = 0
            stdout = BrokenStream()
            stderr = EmptyStream()

            def poll(self):
                return self.returncode

            def wait(self, timeout=None):
                return self.returncode

        with mock.patch("scripts.status.subprocess.Popen", return_value=FakeProcess()), \
             mock.patch("scripts.status._stop_process_group"):
            with self.assertRaisesRegex(status.OmauditError, "Unable to read Omaudit stdout"):
                status._run_process_bounded(
                    ["omaudit"], timeout=1, stdout_limit=4096, stderr_limit=1024,
                )


if __name__ == "__main__":
    unittest.main()
