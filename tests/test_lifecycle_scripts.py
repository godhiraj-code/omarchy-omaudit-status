import unittest
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LifecycleScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.install = (ROOT / "scripts" / "install-local.sh").read_text(encoding="utf-8")
        cls.remove = (ROOT / "scripts" / "remove-local.sh").read_text(encoding="utf-8")

    def test_install_rescans_before_enable_and_arms_rollback_before_copy(self):
        rescan = 'omarchy-shell shell rescanPlugins'
        copy = 'cp -a -- "$SOURCE_DIR/." "$TARGET_DIR"'
        cleanup = 'cleanup_new_copy() {'
        remove_copy = 'rm -rf -- "$TARGET_DIR"'
        trap = 'trap cleanup_new_copy ERR'
        enable = 'omarchy plugin enable "$PLUGIN_ID" --section right'
        rescan_positions = [
            index for index in range(len(self.install))
            if self.install.startswith(rescan, index)
        ]
        self.assertEqual(len(rescan_positions), 2)
        cleanup_rescan, pre_enable_rescan = rescan_positions
        self.assertLess(self.install.index(trap), self.install.index(copy))
        self.assertLess(self.install.index(cleanup), self.install.index(remove_copy))
        self.assertLess(self.install.index(remove_copy), cleanup_rescan)
        self.assertLess(cleanup_rescan, self.install.index(trap))
        self.assertLess(self.install.index(trap), pre_enable_rescan)
        self.assertLess(pre_enable_rescan, self.install.index(enable))

    @unittest.skipUnless(os.name == "posix", "isolated Bash lifecycle probes run on POSIX")
    def test_actual_partial_copy_failure_rolls_back_and_allows_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            isolated = Path(directory)
            fake_bin = isolated / "bin"
            fake_bin.mkdir()
            commands = {
                "omarchy": '#!/bin/bash\nprintf "%s\\n" "$*" >> "$TEST_LOG"\n',
                "omaudit": '#!/bin/bash\nexit 0\n',
                "omarchy-shell": '#!/bin/bash\nprintf "rescan\\n" >> "$TEST_LOG"\n',
                "cp": '#!/bin/bash\ntarget="${@: -1}"\n'
                      'mkdir -p "$target"\nprintf partial > "$target/partial"\nexit 17\n',
            }
            for name, content in commands.items():
                path = fake_bin / name
                path.write_text(content, encoding="utf-8")
                path.chmod(0o700)
            env = {**os.environ, "HOME": str(isolated), "XDG_CONFIG_HOME": str(isolated / "config"),
                   "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"],
                   "TEST_LOG": str(isolated / "log")}
            target = isolated / "config/omarchy/plugins/godhiraj.omaudit-status"
            result = subprocess.run(["bash", str(ROOT / "scripts/install-local.sh")],
                                    cwd=isolated, env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 17)
            self.assertFalse(target.exists(), "partial copy survived failure")
            self.assertNotIn("enable", (isolated / "log").read_text())
            # A successful fake copy proves retry behavior without copying the repo/.git.
            (fake_bin / "cp").write_text('#!/bin/bash\nprintf complete > "${@: -1}/complete"\n')
            result = subprocess.run(["bash", str(ROOT / "scripts/install-local.sh")],
                                    cwd=isolated, env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((target / "complete").read_text(), "complete")
            result = subprocess.run(["bash", str(ROOT / "scripts/install-local.sh")],
                                    cwd=isolated, env=env, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((target / "complete").read_text(), "complete")

    def test_remove_is_explicit_and_noninteractive(self):
        self.assertIn('omarchy plugin disable "$PLUGIN_ID"', self.remove)
        self.assertIn('omarchy plugin remove "$PLUGIN_ID" --yes', self.remove)

    def test_helpers_do_not_escalate_privileges_or_edit_shell_json_directly(self):
        combined = self.install + self.remove
        self.assertNotIn("sudo", combined)
        self.assertNotIn("pkexec", combined)
        self.assertNotIn("shell.json", combined)


if __name__ == "__main__":
    unittest.main()
