# Threat Model

## Trust boundary

Omaudit Status and Omaudit run unsandboxed with the current user's permissions. Omaudit Status is a status UI, not malware detection or a sandbox. Omaudit remains the authority for scanning and grading plugins; Omaudit Status does not reimplement those decisions.

The default scan covers third-party plugins in the user's Omarchy plugin directory. First-party Omarchy plugins are included only when the user explicitly enables that setting; this avoids presenting expected broad capabilities in stock shell components as third-party drift.

The adapter invokes Omaudit with a fixed argument vector. The optional built-in flag only appends the fixed `--all` argument. No plugin-controlled value is evaluated by a shell.

## Deliberately excluded actions

Omaudit Status performs no automatic installation, baseline acceptance, pin, removal, disable, privilege, or network action. Remediation is never silent: the user reviews and chooses remediation through Omaudit in an interactive terminal.

## Failure and disclosure handling

Malformed output, missing Omaudit, scan timeouts, and oversized output fail visibly in a non-green UI state. On the supported Omarchy Linux runtime, the adapter streams both pipes concurrently, retaining at most 8 MiB of stdout and 64 KiB of stderr before terminating Omaudit's isolated process group. Saved fixture input has the same 8 MiB ceiling. Adapter JSON is ASCII-safe so Quickshell's arbitrary byte chunks cannot split Unicode code points. The QML service independently consumes output in chunks, retains at most 2 MiB characters of minimized stdout, drains stderr without retaining it, and uses a forced stop after overflow so scanning cannot wedge. These failures are not presented as a clean scan.

The first-party inclusion setting is part of scan identity. Changing it immediately invalidates the visible result. Output from a scan started under an older scope is discarded, and at most one replacement scan is queued after the active process exits.

Before data reaches QML, the adapter strips filesystem paths, full baseline documents, and evidence snippets. The UI receives only the minimized status data needed to explain the result.
