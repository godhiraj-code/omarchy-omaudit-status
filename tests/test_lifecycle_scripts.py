import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LifecycleScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.install = (ROOT / "scripts" / "install-local.sh").read_text(encoding="utf-8")
        cls.remove = (ROOT / "scripts" / "remove-local.sh").read_text(encoding="utf-8")

    def test_install_rescans_before_enable_and_rolls_back_failed_copy(self):
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
        self.assertLess(self.install.index(copy), self.install.index(cleanup))
        self.assertLess(self.install.index(cleanup), self.install.index(remove_copy))
        self.assertLess(self.install.index(remove_copy), cleanup_rescan)
        self.assertLess(cleanup_rescan, self.install.index(trap))
        self.assertLess(self.install.index(trap), pre_enable_rescan)
        self.assertLess(pre_enable_rescan, self.install.index(enable))

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
