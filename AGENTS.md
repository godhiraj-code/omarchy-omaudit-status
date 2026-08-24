# Change Discipline

- Follow `docs/plans/2026-08-24-omarchy-omaudit-status.md`.
- This repository is a native UI companion for Omaudit; never reimplement its scanner or grading.
- Prefer the smallest correct diff. Do not restructure unrelated code.
- No telemetry, network service, automatic installer, sudo, or silent remediation.
- Never interpolate plugin-controlled values into a shell command.
- Keep the Python adapter standard-library-only.
- Add or update tests with every behavior change.
- Do not push, publish, open pull requests, or submit catalog entries without explicit approval.
