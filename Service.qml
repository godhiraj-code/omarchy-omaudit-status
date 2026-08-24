import QtQuick
import Quickshell
import Quickshell.Io
import "StatusModel.js" as StatusModel

Item {
  id: root

  property var shell: null
  property var manifest: null
  property var status: StatusModel.errorDocument("Waiting for first capability review")
  property bool scanning: false
  property int refreshIntervalSec: 900
  property bool includeBuiltins: false

  readonly property string adapterPath: manifest && manifest.__sourceDir
    ? String(manifest.__sourceDir).replace(/\/$/, "") + "/scripts/status.py"
    : ""

  property string _stdout: ""
  property bool _startupScanStarted: false

  function configure(settings) {
    var configured = settings && settings.refreshIntervalSec !== undefined
      ? Number(settings.refreshIntervalSec) : 900
    if (!isFinite(configured)) configured = 900
    refreshIntervalSec = Math.max(60, Math.min(3600, Math.round(configured)))
    includeBuiltins = !!(settings && settings.includeBuiltins === true)
  }

  function refresh() {
    if (scanning || scanProcess.running || adapterPath === "") return false
    _stdout = ""
    var argv = ["python3", adapterPath]
    if (includeBuiltins) argv.push("--include-builtins")
    scanProcess.command = argv
    scanning = true
    scanProcess.running = true
    return true
  }

  function startupScan() {
    if (_startupScanStarted) return
    if (refresh()) _startupScanStarted = true
  }

  function review() {
    Quickshell.execDetached(["omarchy-launch-floating-terminal-with-presentation", "omaudit check"])
  }

  function applyOutput(raw) {
    var parsed = StatusModel.validateDocument(String(raw || ""))
    status = parsed.document
    return parsed.valid
  }

  onManifestChanged: Qt.callLater(root.startupScan)
  Component.onCompleted: Qt.callLater(root.startupScan)

  Timer {
    interval: root.refreshIntervalSec * 1000
    running: true
    repeat: true
    onTriggered: root.refresh()
  }

  Process {
    id: scanProcess
    running: false
    command: []

    stdout: StdioCollector {
      id: scanStdout
      waitForEnd: true
      onStreamFinished: root._stdout = text
    }

    // Drain stderr separately so it cannot leak into the status document or
    // the shell's inherited output. Omaudit Status intentionally never renders it.
    stderr: StdioCollector {
      id: scanStderr
      waitForEnd: true
    }

    onExited: function(exitCode) {
      // A complete minimized document remains authoritative even if a future
      // adapter uses a non-zero exit. Invalid stdout always fails visibly.
      var valid = root.applyOutput(String(scanStdout.text || root._stdout || ""))
      if (!valid && exitCode !== 0)
        root.status = StatusModel.errorDocument("Omaudit Status adapter process failed")
      root.scanning = false
    }
  }

  IpcHandler {
    target: "omaudit-status"

    function refresh(): string {
      return root.refresh() ? "started" : (root.scanning ? "busy" : "unavailable")
    }

    function status(): string {
      return StatusModel.ipcStatus(root.status, root.scanning)
    }

    function review(): string {
      root.review()
      return "opened"
    }
  }
}
