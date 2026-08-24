# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |
| Earlier or unreleased development versions | No |

Security fixes are made for the current `0.1.x` line. Upgrade to its latest patch release before reporting a problem that may already be fixed.

## Reporting a vulnerability

Do not disclose a suspected vulnerability in a public issue. Do not include secrets, credentials, private paths, private baseline data, or third-party plugin source in any public report.

- Open a minimal private GitHub Security Advisory for this repository. Include only the information needed to reproduce and assess the issue, redact sensitive values, and share additional evidence privately when requested.

Please include the affected Omaudit Status and Omaudit versions, expected and observed behavior, reproduction steps using sanitized data, and the likely impact. Allow reasonable time for acknowledgement, investigation, and a coordinated fix before public disclosure.

## Scope and security boundary

Omaudit Status is a local status UI for Omaudit capability and risk drift. It is not malware detection, a sandbox, or proof that a plugin is safe. Omaudit Status and Omaudit run with the current user's permissions.

Omaudit Status performs no telemetry, network service, automatic remediation, baseline acceptance, plugin installation/removal, or privileged action. See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) for the detailed trust boundary and limitations.
