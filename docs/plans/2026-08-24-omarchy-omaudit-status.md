# Omaudit Status Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a native Omarchy Quattro bar widget that continuously summarizes installed shell-plugin risk and capability drift by consuming Omaudit's machine-readable output without duplicating its scanner.

**Architecture:** A dependency-free Python adapter invokes `omaudit check --json` with a fixed argv, optionally adding `--all` only when the user explicitly enables first-party auditing. It accepts Omaudit exit codes 0 and 1, validates and strips the upstream payload, and emits a small stable JSON status contract. The plugin declares both `service` and `bar-widget`: one shell-level singleton service owns polling and process execution, while every monitor's widget reads that shared state and renders a risk-colored shield with a keyboard-friendly panel. All remediation stays inside Omaudit's interactive terminal workflow; the widget never silently accepts a baseline, disables a plugin, removes code, or performs privileged actions.

**Tech Stack:** Omarchy 4/Quattro, Quickshell QML, JavaScript, Python 3 standard library, unittest, Node.js tests for pure JavaScript helpers.

---

## Product boundary

### In scope

- Detect whether `omaudit` is available.
- Scan user plugins through `omaudit check --json`; optionally include first-party plugins through `omaudit check --json --all`.
- Summarize total, unchanged, changed, untracked and composition-risk counts.
- Show the worst current grade and per-plugin status.
- Audit third-party plugins by default; make first-party Omarchy auditing an explicit opt-in because stock first-party plugins legitimately exercise broad shell capabilities and otherwise create a noisy first run.
- Sort changed plugins first, then untracked, then unchanged; within a status sort worst grade first.
- Refresh on panel open, by middle/right click, through IPC, and on a configurable timer.
- Open `omaudit check` in an Omarchy floating terminal for explicit human review.
- Fail closed in the UI when output is malformed, the process times out, or Omaudit exits unexpectedly.
- Avoid exposing plugin filesystem paths or full baseline documents to QML.

### Non-goals

- Reimplementing Omaudit scanning or grading.
- Claiming sandboxing or malware detection.
- Automatically installing Omaudit.
- Automatically accepting baselines, pinning, disabling or removing plugins.
- Network services, telemetry, cloud accounts or privileged setup.
- Supporting pre-Quattro Omarchy releases.

## Stable adapter contract

`scripts/status.py` prints exactly one JSON object:

```json
{
  "schemaVersion": 1,
  "ok": true,
  "installed": true,
  "scannedAt": "2026-08-24T12:00:00+00:00",
  "statusText": "1 plugin changed",
  "worstGrade": "D",
  "totals": {
    "plugins": 8,
    "unchanged": 5,
    "changed": 1,
    "notTracked": 2,
    "compositionRisks": 1
  },
  "plugins": [
    {
      "id": "example.weather",
      "name": "Weather",
      "version": "1.2.0",
      "grade": "D",
      "score": 41,
      "status": "changed",
      "firstParty": false,
      "added": ["net.outbound"],
      "composition": ["composition: credentials plus outbound network"],
      "evidence": {
        "net.outbound": {"file": "Panel.qml", "line": 10}
      }
    }
  ],
  "error": ""
}
```

The error form remains valid JSON and uses `ok: false`. Missing Omaudit uses `installed: false`; malformed output, timeout and unexpected exit use `installed: true` when the executable exists.

---

### Task 1: Create repository contracts and representative fixtures

**Objective:** Establish the plugin manifest, explicit threat model and fixture contracts before implementation.

**Files:**
- Create: `manifest.json`
- Create: `docs/THREAT_MODEL.md`
- Create: `tests/fixtures/unchanged.json`
- Create: `tests/fixtures/changed.json`
- Create: `tests/fixtures/malformed.txt`

**Steps:**

1. Write a schema-version-1 manifest with id `godhiraj.omaudit-status`, kinds `service` and `bar-widget`, entry points `Service.qml` and `Panel.qml`, `keepLoaded: true`, right-side default placement, a configurable refresh interval from 60 to 3600 seconds, and `includeBuiltins` defaulting to false.
2. Document that the plugin and Omaudit share the user's permissions and are not a sandbox.
3. State that all commands use fixed argv and no plugin-controlled value is evaluated by a shell.
4. Add fixtures mirroring Omaudit `_check_plugin` output for clean, changed, untracked and composition-risk cases.
5. Run `python -m json.tool manifest.json` and each JSON fixture; expected exit 0.
6. Run Omarchy's validator on the real Omarchy host after entry points exist.

### Task 2: Implement and test the status adapter

**Objective:** Convert Omaudit output into a stable, privacy-minimized status document.

**Files:**
- Create: `scripts/status.py`
- Create: `tests/test_status.py`

**TDD steps:**

1. Write tests for clean results, changed results, missing Omaudit, malformed JSON, timeout, unexpected exit and evidence normalization.
2. Run `python -m unittest tests.test_status -v`; expected failure because the adapter does not exist.
3. Implement `build_status(results, scanned_at)`, `run_omaudit()` and `main()` using only the standard library.
4. Invoke Omaudit with `subprocess.run(["omaudit", "check", "--json"], shell=False, capture_output=True, text=True, timeout=120)`; add `--all` only when the adapter receives the explicit `--include-builtins` flag.
5. Treat exit codes 0 and 1 as valid because Omaudit uses 1 for findings.
6. Validate top-level list and required per-item fields; skip invalid rows rather than forwarding arbitrary objects.
7. Strip `dir`, full `baseline`, snippets and unneeded upstream fields.
8. Add `--input FILE` for deterministic fixture testing only; it reads saved Omaudit JSON and performs no subprocess call. Add `--include-builtins` as the only switch that enables Omaudit's `--all` mode.
9. Run `python -m unittest tests.test_status -v`; expected all pass.
10. Run `python scripts/status.py --input tests/fixtures/changed.json | python -m json.tool`; expected valid normalized JSON.

### Task 3: Implement and test the pure QML model helpers

**Objective:** Keep parsing, labels, sorting and color-state decisions deterministic and independently testable.

**Files:**
- Create: `Model.js`
- Create: `tests/model-test.mjs`

**TDD steps:**

1. Write Node tests for default status, valid parsing, malformed parsing, worst-grade ordering, status sorting, summary labels and risk-state mapping.
2. Run `node --test tests/model-test.mjs`; expected failure because `Model.js` does not exist.
3. Implement pure ES-compatible functions and CommonJS exports guarded by `typeof module !== "undefined"`.
4. Ensure malformed adapter output returns a visible error state, never a clean state.
5. Run `node --test tests/model-test.mjs`; expected all pass.

### Task 4: Build the native Quickshell service and panel

**Objective:** Deliver a theme-aware native widget with safe refresh and explicit review actions.

**Files:**
- Create: `Service.qml`
- Create: `Panel.qml`

**Steps:**

1. Implement `Service.qml` as the single shell-level service with a periodic Timer and one Quickshell `Process` calling `python3 <plugin-source>/scripts/status.py` as an argv array, appending `--include-builtins` only when the boolean widget setting is true.
2. Resolve the helper relative to the plugin component URL or injected manifest source without depending on `$OMARCHY_PATH`, because this is a user plugin.
3. Capture stdout and stderr separately; accept valid JSON regardless of adapter exit result, otherwise expose an error.
4. Prevent overlapping scans.
5. Implement a `Panel` bar widget following first-party Omarchy patterns: obtain shared state through `bar?.shell?.serviceFor("godhiraj.omaudit-status")`, then use `BarIconButton`, `KeyboardPanel`, `PanelKeyCatcher`, `PanelHero`, themed colors and keyboard navigation. Do not instantiate `Service.qml` inside the widget.
6. Display a green/amber/red/dim shield based on changed, untracked, composition risk and error state.
7. Show summary counts and a bounded plugin list sorted by the adapter.
8. Provide refresh via middle/right click, key `r`, panel-open refresh and IPC `refresh`.
9. Provide “Review in terminal” via a fixed command invoking `omarchy-launch-floating-terminal-with-presentation "omaudit check"`; never inject plugin data into the command.
10. Show installation instructions when Omaudit is missing but do not download or execute an installer.
11. Run `qmllint`/`qmlformat --check` if available; otherwise use Omarchy's shell tests and live load as the authority.

### Task 5: Documentation, validation and real-host verification

**Objective:** Prove the repository installs, loads and behaves correctly on Omarchy 4.

**Files:**
- Create: `README.md`
- Create: `LICENSE`
- Create: `AGENTS.md`
- Create: `.gitignore`
- Create: `scripts/install-local.sh`
- Create: `scripts/remove-local.sh`

**Steps:**

1. Document prerequisites, reviewed Omaudit install path, add/enable commands, keyboard controls and removal.
2. Make local install/remove scripts explicit and reversible; no sudo and no config overwrites.
3. Run all Python and Node tests locally.
4. Run `git diff --check` and a secret-shaped content scan.
5. Copy the repository to the real Omarchy desktop in a temporary path.
6. Run `omarchy plugin validate <path>`; expected exit 0.
7. Install Omaudit from a reviewed local checkout or release installer only after verifying its version and source.
8. Add Omaudit Status through `omarchy plugin add <local-git-url-or-reviewed-source> --enable --yes`, or symlink only for development if the add command requires a remote.
9. Restart the shell if the known Quattro hot-reload cache issue prevents fresh QML from loading.
10. Verify `omarchy plugin list --json` reports `godhiraj.omaudit-status` enabled and active.
11. Run IPC refresh and status calls.
12. Capture a screenshot showing the bar icon and opened panel; visually verify clean, missing-dependency and fixture-induced changed states where feasible.
13. Remove the development installation if it destabilizes the shell; preserve logs and report the blocker honestly.

## Acceptance criteria

- `manifest.json` passes Omarchy's native plugin validator.
- Python adapter tests cover success and all failure modes.
- JavaScript model tests cover status parsing and ordering.
- The adapter never executes a shell or forwards plugin-controlled paths/baselines into QML.
- Missing or broken Omaudit is visibly non-green.
- Findings exit code 1 still produces a valid changed state.
- The default scan excludes first-party plugins; enabling `includeBuiltins` adds them explicitly.
- The widget loads in the real Omarchy 4 shell without breaking the bar.
- On multiple monitors, all widgets share one service and exactly one Omaudit scan process runs at a time.
- Refresh and review actions work from the panel.
- No baseline acceptance, plugin removal, package install or privilege escalation happens without an explicit terminal interaction.
- README and threat model accurately describe limitations.

## Release gate

Do not push, publish, submit to the Omarchy catalog or announce the plugin without Dhiraj's explicit approval. A local verified repository is the completion target for this implementation run.
