# Omaudit Status

Omaudit Status adds native Omarchy 4/Quattro bar status for [Omaudit](https://github.com/omarchy-forge/omaudit) plugin capability and risk drift. It is a small status and review interface—not another scanner. Omaudit performs the scan and grading; Omaudit Status converts its machine-readable result into a shield indicator and a keyboard-friendly panel.

> **Important:** capability review is not malware detection. A capability finding says what plugin code can do, or what changed from a reviewed baseline. It does not prove that code is malicious or safe, and Omaudit Status does not sandbox plugins.

## Requirements

- Omarchy 4 with the Quattro shell
- Python 3.11 or newer
- Omaudit v0.1.0 or newer
- Node.js only when running development tests

Omaudit Status does **not** install or update Omaudit. Follow [Omaudit's official installation instructions](https://github.com/omarchy-forge/omaudit#install), review that project and its release source, then confirm `omaudit` is available on your path. No `sudo` or bundled installer is required for Omaudit Status.

## Installation

After installing Omaudit, add and enable the plugin through Omarchy:

```sh
omarchy plugin add https://github.com/godhiraj-code/omarchy-omaudit-status --enable --yes
```

## Local development installation

From a local checkout, the included helper validates the source, refuses to overwrite an existing installation, copies it locally, rescans local plugins, and enables it through Omarchy:

```sh
./scripts/install-local.sh
```

Equivalent manual commands:

```sh
SOURCE=/path/to/omaudit-status
omarchy plugin validate "$SOURCE"
mkdir -p ~/.config/omarchy/plugins
cp -a "$SOURCE" ~/.config/omarchy/plugins/godhiraj.omaudit-status
omarchy-shell shell rescanPlugins
omarchy plugin enable godhiraj.omaudit-status --section right
```

Instead of copying, you may clone a local Git checkout directly into `~/.config/omarchy/plugins/godhiraj.omaudit-status`. Validate the directory and run `omarchy-shell shell rescanPlugins` before enabling it.

## Usage

- **Click** the shield to open or close the status popup.
- **Middle-click or right-click** the shield to refresh immediately.
- Press **`r`** while the popup is open to refresh.
- Press **Escape** to close the popup.
- Choose **Review in terminal** to open Omaudit's interactive `omaudit check` review flow. Omaudit Status never accepts a baseline or remediates findings itself.

The panel summarizes changed, not-tracked, unchanged, and composition-risk counts and shows the worst current grade. Missing Omaudit, malformed output, timeouts, and unexpected exits remain visible as non-green errors rather than clean results.

### Settings

- **Refresh interval:** 60–3600 seconds; default 900 seconds.
- **Include first-party Omarchy plugins:** opt-in; disabled by default.

Third-party plugins are the default because stock Omarchy components legitimately use broad shell capabilities. Including them on the first scan can create noisy results that obscure third-party capability drift.

## Screenshot

The bar icon, bounded popup, keyboard close action, terminal review flow, two-monitor rendering, and green/amber/red visual states were validated on a real Omarchy 4 desktop. Screenshots are intentionally not committed because they included the operator's live desktop context.

## Removal

Use Omarchy's plugin commands rather than deleting live shell files manually:

```sh
./scripts/remove-local.sh
```

Equivalent manual commands:

```sh
omarchy plugin disable godhiraj.omaudit-status
omarchy plugin remove godhiraj.omaudit-status --yes
```

Omaudit is a separate tool and is not removed, installed, or updated by these commands.

## Development and verification

From the repository root:

```sh
# Python adapter and QML contract tests
python -m unittest discover -s tests -p "test_*.py" -v

# Pure status-model test
node tests/status-model-test.mjs

# Adapter fixture smoke test; output must be valid JSON
python scripts/status.py --input tests/fixtures/changed.json | python -m json.tool

# Manifest and fixture JSON validation
python -m json.tool manifest.json >/dev/null
for fixture in tests/fixtures/*.json; do python -m json.tool "$fixture" >/dev/null; done

# Official Omarchy plugin validation (run on an Omarchy 4 host)
omarchy plugin validate .
```

Node.js is not needed at runtime. The adapter uses only the Python standard library.

## Security and limitations

Omaudit Status and Omaudit run with the current user's permissions; neither is a sandbox. Omaudit Status invokes Omaudit with a fixed argument vector, minimizes the data passed to QML, and does not evaluate plugin-controlled values in a shell.

Omaudit Status has:

- no telemetry or network service;
- no automatic remediation, plugin disable/removal, or privileged action;
- no automatic baseline acceptance;
- no malware-detection claim.

Read the full [threat model](docs/THREAT_MODEL.md) and [security policy](SECURITY.md) before reporting a vulnerability. Treat grades and drift as review signals, not proof of safety or maliciousness.

## License

[MIT](LICENSE) © 2026 Dhiraj Das
