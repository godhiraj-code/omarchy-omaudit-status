"""POSIX adapter cancellation with a real fake scanner and stubborn descendant."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux process-state probe")
class CancellationTests(unittest.TestCase):
    def test_sigterm_and_sigint_clean_scanner_group_before_adapter_exit(self):
        for cancel_signal in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(signal=cancel_signal), tempfile.TemporaryDirectory() as directory:
                isolated = Path(directory)
                scanner = isolated / "omaudit"
                pidfile = isolated / "pids.json"
                scanner.write_text(
                    f"#!{sys.executable}\n"
                    "import json, os, signal, subprocess, sys, time\n"
                    "from pathlib import Path\n"
                    "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                    "child = subprocess.Popen([sys.executable, '-c', "
                    "'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)'])\n"
                    "Path(os.environ['TEST_PID_FILE']).write_text(json.dumps([os.getpid(), child.pid]))\n"
                    "time.sleep(60)\n", encoding="utf-8")
                scanner.chmod(0o700)
                env = {**os.environ, "PATH": str(isolated) + os.pathsep + os.environ["PATH"],
                       "HOME": str(isolated), "XDG_CONFIG_HOME": str(isolated / "config"),
                       "TEST_PID_FILE": str(pidfile)}
                adapter = subprocess.Popen([sys.executable, "-B", str(ROOT / "scripts/status.py")],
                                           cwd=isolated, env=env, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE)
                pids = []
                try:
                    deadline = time.monotonic() + 5
                    while not pidfile.exists() and time.monotonic() < deadline:
                        time.sleep(0.02)
                    self.assertTrue(pidfile.exists(), "fake scanner did not start")
                    pids = json.loads(pidfile.read_text())
                    started = time.monotonic()
                    adapter.send_signal(cancel_signal)
                    stdout, stderr = adapter.communicate(timeout=5)
                    self.assertLess(time.monotonic() - started, 4)
                    # Zombies are no longer executing; their adoption/reaping is init's job.
                    for pid in pids:
                        proc = Path(f"/proc/{pid}/stat")
                        self.assertTrue(not proc.exists() or proc.read_text().split(") ")[1][0] == "Z",
                                        f"scanner descendant {pid} still running")
                    self.assertEqual(adapter.returncode, 0, stderr)
                    document = json.loads(stdout)
                    self.assertFalse(document["ok"])
                    self.assertIn("cancel", document["error"].lower())
                finally:
                    if adapter.poll() is None:
                        adapter.kill()
                    adapter.communicate(timeout=5)
                    if pids:
                        try:
                            os.killpg(pids[0], signal.SIGKILL)
                        except ProcessLookupError:
                            pass
