import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class QmlContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        cls.service = (ROOT / "Service.qml").read_text(encoding="utf-8")
        cls.panel = (ROOT / "Panel.qml").read_text(encoding="utf-8")

    def test_manifest_declares_singleton_service_and_bar_widget(self):
        self.assertEqual(self.manifest["kinds"], ["service", "bar-widget"])
        self.assertTrue(self.manifest["keepLoaded"])
        self.assertEqual(self.manifest["entryPoints"]["service"], "Service.qml")
        self.assertEqual(self.manifest["entryPoints"]["barWidget"], "Panel.qml")
        self.assertFalse(self.manifest["barWidget"]["allowMultiple"])

    def test_service_uses_fixed_paths_arguments_and_separate_collectors(self):
        self.assertIn('manifest.__sourceDir', self.service)
        self.assertIn('var argv = ["python3", adapterPath]', self.service)
        self.assertIn('argv.push("--include-builtins")', self.service)
        self.assertIn('stdout: StdioCollector', self.service)
        self.assertIn('stderr: StdioCollector', self.service)
        self.assertIn('if (scanning || scanProcess.running', self.service)
        self.assertIn('Math.max(60, Math.min(3600', self.service)
        self.assertIn('target: "omaudit-status"', self.service)
        self.assertIn('["omarchy-launch-floating-terminal-with-presentation", "omaudit check"]', self.service)
        for forbidden in ("sudo", "pkexec", "omaudit baseline", "omaudit add", "omaudit install"):
            self.assertNotIn(forbidden, self.service)

    def test_panel_only_reads_the_shared_service_and_exposes_required_actions(self):
        self.assertIn('serviceFor("godhiraj.omaudit-status")', self.panel)
        self.assertNotIn("Service {", self.panel)
        self.assertIn('Qt.MiddleButton || buttonCode === Qt.RightButton', self.panel)
        self.assertIn('text === "r" || text === "R"', self.panel)
        self.assertIn('onCloseRequested: root.close()', self.panel)
        self.assertIn('onActivateRequested: root.activateAction()', self.panel)
        self.assertIn('label: "Worst"', self.panel)
        self.assertIn('Omaudit is missing.', self.panel)
        self.assertIn('contentWidth: popup.fittedContentWidth', self.panel)
        self.assertIn('contentHeight: popup.fittedContentHeight', self.panel)


if __name__ == "__main__":
    unittest.main()
