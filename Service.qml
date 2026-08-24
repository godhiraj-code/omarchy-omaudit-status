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
  readonly property int maxAdapterOutputChars: 2 * 1024 * 1024

  readonly property string adapterPath: manifest && manifest.__sourceDir
    ? String(manifest.__sourceDir).replace(/\/$/, "") + "/scripts/status.py"
    : ""

  property string _stdout: ""
  property bool _outputOverflow: false
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
    _outputOverflow = false
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

  function ingestStdout(chunk) {
    if (_outputOverflow) return
    var text = String(chunk || "")
    if (_stdout.length + text.length > maxAdapterOutputChars) {
      _outputOverflow = true
      _stdout = ""
      status = StatusModel.errorDocument("Omaudit Status adapter output exceeded the size limit")
      // Untrusted oversized output is not given an open-ended graceful-exit
      // window. SIGKILL guarantees onExited runs and refreshes cannot wedge.
      if (scanProcess.running) scanProcess.signal(9)
      return
    }
    _stdout += text
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

    stdout: SplitParser {
      splitMarker: ""
      onRead: function(chunk) { root.ingestStdout(chunk) }
    }

    // Drain and discard stderr chunk-by-chunk. It never enters a retained QML
    // buffer, the status document, or the shell's inherited output.
    stderr: SplitParser {
      splitMarker: ""
      onRead: function(_chunk) {}
    }

    onExited: function(exitCode) {
      if (root._outputOverflow) {
        root.scanning = false
        return
      }
      // A complete minimized document remains authoritative even if a future
      // adapter uses a non-zero exit. Invalid stdout always fails visibly.
      var valid = root.applyOutput(root._stdout)
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
