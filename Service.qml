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
  property double nowMs: Date.now()
  readonly property int staleAfterSec: refreshIntervalSec + 150
  readonly property int maxAdapterOutputChars: 2 * 1024 * 1024

  readonly property string adapterPath: manifest && manifest.__sourceDir
    ? String(manifest.__sourceDir).replace(/\/$/, "") + "/scripts/status.py"
    : ""

  property string _stdout: ""
  property bool _outputOverflow: false
  property bool _startupScanStarted: false
  property bool _refreshPending: false
  property string _failure: ""
  property int _configurationGeneration: 0
  property int _activeGeneration: -1

  function configure(settings) {
    var configured = settings && settings.refreshIntervalSec !== undefined
      ? Number(settings.refreshIntervalSec) : 900
    if (!isFinite(configured)) configured = 900
    var configuredInterval = Math.max(60, Math.min(3600, Math.round(configured)))
    var configuredBuiltins = !!(settings && settings.includeBuiltins === true)
    var scopeChanged = includeBuiltins !== configuredBuiltins
    refreshIntervalSec = configuredInterval
    includeBuiltins = configuredBuiltins
    if (scopeChanged) {
      _configurationGeneration += 1
      status = StatusModel.errorDocument("Audit scope changed; waiting for a scan using the current settings")
      if (scanning || scanProcess.running) _refreshPending = true
      else Qt.callLater(root.refresh)
    }
  }

  function refresh() {
    if (scanning || scanProcess.running || adapterPath === "") return false
    _stdout = ""
    _outputOverflow = false
    _failure = ""
    _activeGeneration = _configurationGeneration
    var argv = ["python3", adapterPath]
    if (includeBuiltins) argv.push("--include-builtins")
    scanProcess.command = argv
    scanning = true
    nowMs = Date.now()
    watchdog.restart()
    startDeadline.restart()
    scanProcess.running = true
    return true
  }

  function startupScan() {
    if (_startupScanStarted) return
    if (refresh()) _startupScanStarted = true
  }

  function review() {
    if (status.installed === false) return false
    Quickshell.execDetached(["omarchy-launch-floating-terminal-with-presentation",
      includeBuiltins ? "omaudit check --all" : "omaudit check"])
    return true
  }

  function finishScan() {
    watchdog.stop()
    startDeadline.stop()
    killDeadline.stop()
    _stdout = ""
    scanning = false
    nowMs = Date.now()
    var pending = _refreshPending
    _refreshPending = false
    if (pending) Qt.callLater(root.refresh)
  }

  function failScan(message) {
    if (!scanning) return
    if (_failure === "") _failure = message
    _stdout = ""
    if (StatusModel.shouldPublishScan(_activeGeneration, _configurationGeneration))
      status = StatusModel.errorDocument(_failure)
    watchdog.stop()
    startDeadline.stop()
    // v0.2.1 Process.signal uses the PID directly: never signal a zero PID
    // while QProcess is starting. Give Python time to clean its scanner group.
    if (scanProcess.running) {
      if (Number(scanProcess.processId) > 0) scanProcess.signal(15)
      killDeadline.restart()
    } else finishScan()
  }

  function startTimedOut() {
    failScan("Omaudit Status adapter did not start within 10 seconds; check python3")
  }

  function scanTimedOut() {
    failScan("Omaudit Status adapter timed out after 150 seconds")
  }

  function hardStop() {
    if (!scanning) return
    if (!scanProcess.running) finishScan()
    else if (Number(scanProcess.processId) > 0) scanProcess.signal(9)
    // Keep overlap protection until Process confirms termination.
  }

  function applyOutput(raw) {
    var parsed = StatusModel.validateDocument(String(raw || ""))
    status = parsed.document
    return parsed.valid
  }

  function ingestStdout(chunk) {
    if (_outputOverflow || _failure !== "" || !scanning) return
    var text = String(chunk || "")
    if (_stdout.length + text.length > maxAdapterOutputChars) {
      _outputOverflow = true
      _stdout = ""
      failScan("Omaudit Status adapter output exceeded the size limit")
      return
    }
    _stdout += text
  }

  onManifestChanged: Qt.callLater(root.startupScan)
  Component.onCompleted: Qt.callLater(root.startupScan)

  Timer {
    id: startDeadline
    interval: 10000
    onTriggered: root.startTimedOut()
  }

  Timer {
    id: watchdog
    interval: 150000
    onTriggered: root.scanTimedOut()
  }

  Timer {
    id: killDeadline
    interval: 5000
    onTriggered: root.hardStop()
  }

  Timer {
    interval: 1000
    running: true
    repeat: true
    onTriggered: root.nowMs = Date.now()
  }

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

    onStarted: {
      startDeadline.stop()
      if (root._failure !== "") root.failScan(root._failure)
    }

    // v0.2.1 FailedToStart emits runningChanged, not exited or a public
    // errorOccurred signal. Normal completion emits exited first.
    onRunningChanged: {
      if (!running && root.scanning) {
        root.failScan("Omaudit Status adapter failed to start; check python3 and the adapter path")
      }
    }

    onExited: function(exitCode, exitStatus) {
      var resultIsCurrent = StatusModel.shouldPublishScan(root._activeGeneration,
                                                          root._configurationGeneration)
      if (resultIsCurrent && root._failure === "") {
        // QProcess NormalExit is 0. Omaudit's findings exit is handled inside
        // Python; the adapter itself must finish normally with exit code zero.
        if (exitCode !== 0 || exitStatus !== 0)
          root.status = StatusModel.errorDocument("Omaudit Status adapter process failed")
        else root.applyOutput(root._stdout)
      }
      root.finishScan()
    }
  }

  IpcHandler {
    target: "omaudit-status"

    function refresh(): string {
      return root.refresh() ? "started" : (root.scanning ? "busy" : "unavailable")
    }

    function status(): string {
      return StatusModel.ipcStatus(root.status, root.scanning, root.nowMs, root.staleAfterSec)
    }

    function review(): string {
      return root.review() ? "opened" : "unavailable"
    }
  }
}
