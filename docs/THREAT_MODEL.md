# Threat Model

## Trust boundary

Omaudit Status and Omaudit run unsandboxed with the current user's permissions. Omaudit Status is a status UI, not malware detection or a sandbox. Omaudit remains the authority for scanning and grading plugins; Omaudit Status does not reimplement those decisions.

The default scan covers third-party plugins in the user's Omarchy plugin directory. First-party Omarchy plugins are included only when the user explicitly enables that setting; this avoids presenting expected broad capabilities in stock shell components as third-party drift.

The adapter invokes Omaudit with a fixed argument vector. The optional built-in flag only appends the fixed `--all` argument. No plugin-controlled value is evaluated by a shell.

## Deliberately excluded actions

Omaudit Status performs no automatic installation, baseline acceptance, pin, removal, disable, privilege, or network action. Remediation is never silent: the user reviews and chooses remediation through Omaudit in an interactive terminal.

## Failure and disclosure handling

Malformed output (including non-string raw grades), missing Omaudit, unsuccessful adapter exits, timeouts, and oversized output fail visibly in a non-green UI state. On the supported Omarchy Linux runtime, the adapter streams both pipes concurrently, retaining at most 8 MiB of stdout and 64 KiB of stderr before terminating Omaudit's isolated process group. Saved fixture input has the same 8 MiB ceiling. Adapter JSON is ASCII-safe; field limits count Unicode code points in both layers. The QML service retains at most 2 MiB characters of minimized stdout and drains stderr without retaining it.

The service requires normal adapter exit code zero (Omaudit findings exit 1 remains valid inside Python). Startup and execution deadlines are 10 and 150 seconds. Failure/overflow sends SIGTERM, giving the adapter 5 seconds before SIGKILL. The adapter handles SIGTERM/SIGINT with a cancellation flag established before spawning, then terminates the scanner group with a 0.5-second graceful window and SIGKILL fallback. Linux tests check real scanner and stubborn descendant process states. This is process-group cleanup, not containment: descendants that deliberately escape the group, or a frozen adapter killed before it can handle SIGTERM, cannot be guaranteed cleaned up. Quickshell destruction/reload may also kill the adapter without its cleanup handler. No desktop teardown guarantee is claimed.

Refresh retains prior results with refreshing/age text. A result older than the configured interval plus 150 seconds, or more than 30 seconds in the future, becomes stale and dim. Negative ages within the clock-skew allowance display as zero. Freshness is reevaluated every second while the QML event loop runs. Failed attempts are labeled separately from successful scans. Errors and identities are bounded plain text; bidi/control characters are escaped on display, IDs and grades are separate from plugin names. This does not prevent ordinary Unicode confusables.

Process API evidence checked on 2026-09-05: [Quickshell v0.2.1 documentation](https://quickshell.org/docs/v0.2.1/types/Quickshell.Io/Process/) lists `started`, `exited(exitCode, exitStatus)`, `runningChanged` and `signal(int)`. [The tagged source](https://raw.githubusercontent.com/quickshell-mirror/quickshell/v0.2.1/src/io/process.cpp) shows FailedToStart clears the process and emits `runningChanged` without `exited`; normal finish emits `exited` first. There is no public `errorOccurred` handler used here. Signals are sent only for positive PIDs because the implementation passes the PID directly to `kill`. [Qt documents NormalExit as 0](https://doc.qt.io/qt-6/qprocess.html#ExitStatus-enum). No Quickshell installation is available in this worktree's WSL environment; the target host version, enum delivery and event ordering still require native verification. Node probes execute QML function/handler bodies with Process/Timer doubles, not a QML engine. Unkillable OS processes retain overlap protection until termination is confirmed.

The first-party inclusion setting is part of scan identity. Changing it immediately invalidates the visible result. Output from a scan started under an older scope is discarded, and at most one replacement scan is queued after the active process exits.

Keyboard scrolling uses Qt's documented [Keys.forwardTo](https://doc.qt.io/qt-6/qml-qtquick-keys.html#forwardTo-prop) with a separate item, preserving the host [PanelKeyCatcher dispatcher](https://github.com/basecamp/omarchy/blob/quattro/shell/Ui/PanelKeyCatcher.qml). Actual focus, Escape behavior, and action visibility on small displays remain native verification items. Divergent per-monitor settings remain a host configuration question; singleton ownership is unchanged.

Before data reaches QML, the adapter strips filesystem paths, full baseline documents, and evidence snippets. The UI receives only the minimized status data needed to explain the result.
