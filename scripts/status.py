#!/usr/bin/env python3
"""Privacy-minimizing JSON adapter for ``omaudit check``."""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

COMMAND = ["omaudit", "check", "--json"]
VALID_STATUSES = {"changed", "not-tracked", "unchanged"}
VALID_GRADES = {"", "A", "B", "C", "D", "F"}
STATUS_ORDER = {"changed": 0, "not-tracked": 1, "unchanged": 2}
GRADE_ORDER = {"F": 0, "D": 1, "C": 2, "B": 3, "A": 4, "": 5}
MAX_PLUGINS = 100
MAX_OMAUDIT_STDOUT_BYTES = 8 * 1024 * 1024
MAX_OMAUDIT_STDERR_BYTES = 64 * 1024
READ_CHUNK_BYTES = 64 * 1024
PROCESS_TERMINATE_GRACE_SECONDS = 0.5


class OmauditError(Exception):
    """An expected failure while obtaining Omaudit results."""


def _stop_process_group(process: subprocess.Popen[bytes]) -> None:
    """Terminate the POSIX group; use best-effort cleanup on dev platforms."""
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + PROCESS_TERMINATE_GRACE_SECONDS
        while time.monotonic() < deadline:
            process.poll()
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.02)
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif os.name == "nt":
        # Development-only fallback. Omaudit Status supports Omarchy Linux;
        # Windows Job Object semantics are deliberately outside runtime scope.
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    elif process.poll() is None:
        process.kill()

    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def _run_process_bounded(
    command: list[str],
    *,
    timeout: float,
    stdout_limit: int = MAX_OMAUDIT_STDOUT_BYTES,
    stderr_limit: int = MAX_OMAUDIT_STDERR_BYTES,
) -> subprocess.CompletedProcess[str]:
    """Run a fixed argv while retaining no more than the configured byte caps."""
    group_options: dict[str, Any] = {}
    if os.name == "posix":
        group_options["start_new_session"] = True
    elif os.name == "nt":
        group_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    process = subprocess.Popen(
        command,
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **group_options,
    )
    assert process.stdout is not None
    assert process.stderr is not None

    overflow = threading.Event()
    reader_failed = threading.Event()
    overflow_stream: list[str] = []
    failed_stream: list[str] = []
    overflow_lock = threading.Lock()
    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []

    def drain(stream: Any, chunks: list[bytes], limit: int, label: str) -> None:
        total = 0
        read_chunk = getattr(stream, "read1", None) or stream.read
        try:
            while True:
                chunk = read_chunk(READ_CHUNK_BYTES)
                if not chunk:
                    return
                if total + len(chunk) > limit:
                    with overflow_lock:
                        if not overflow_stream:
                            overflow_stream.append(label)
                    overflow.set()
                    return
                chunks.append(chunk)
                total += len(chunk)
        except (OSError, ValueError):
            with overflow_lock:
                if not failed_stream:
                    failed_stream.append(label)
            reader_failed.set()

    readers = [
        threading.Thread(
            target=drain,
            args=(process.stdout, stdout_chunks, stdout_limit, "stdout"),
            daemon=True,
        ),
        threading.Thread(
            target=drain,
            args=(process.stderr, stderr_chunks, stderr_limit, "stderr"),
            daemon=True,
        ),
    ]
    for reader in readers:
        reader.start()

    deadline = time.monotonic() + timeout
    timed_out = False
    while True:
        if overflow.is_set() or reader_failed.is_set():
            break
        if process.poll() is not None and not any(reader.is_alive() for reader in readers):
            break
        if time.monotonic() >= deadline:
            timed_out = True
            break
        overflow.wait(0.05)

    if overflow.is_set() or reader_failed.is_set() or timed_out:
        _stop_process_group(process)
    else:
        process.wait()
    for reader in readers:
        reader.join(timeout=2)

    if any(reader.is_alive() for reader in readers):
        raise OmauditError("Unable to finish reading Omaudit output")
    process.stdout.close()
    process.stderr.close()

    if timed_out:
        raise subprocess.TimeoutExpired(command, timeout)
    if reader_failed.is_set():
        label = failed_stream[0] if failed_stream else "output"
        raise OmauditError(f"Unable to read Omaudit {label}")
    if overflow.is_set():
        label = overflow_stream[0] if overflow_stream else "output"
        raise OmauditError(f"Omaudit {label} exceeded the size limit")

    try:
        stdout = b"".join(stdout_chunks).decode("utf-8", errors="strict")
        stderr = b"".join(stderr_chunks).decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise OmauditError("Omaudit output was not valid UTF-8") from exc
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _read_saved_output(path: str) -> str:
    """Read a deterministic fixture without allowing an unbounded allocation."""
    with Path(path).open("rb") as source:
        raw = source.read(MAX_OMAUDIT_STDOUT_BYTES + 1)
    if len(raw) > MAX_OMAUDIT_STDOUT_BYTES:
        raise OmauditError("Saved Omaudit output exceeded the size limit")
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise OmauditError("Saved Omaudit output was not valid UTF-8") from exc


def _utc_seconds(value: datetime | None = None) -> str:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat(timespec="seconds")


def _string(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _string_list(value: Any, limit: int, string_limit: int = 300) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _string(item, string_limit)
        if text and text not in seen:
            result.append(text)
            seen.add(text)
            if len(result) == limit:
                break
    return result


def _score(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(number):
        return 0
    return max(0, min(100, int(number)))


def _evidence(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for raw_kind, raw_location in value.items():
        kind = _string(raw_kind, 200)
        if not kind or not isinstance(raw_location, (list, tuple)) or len(raw_location) != 2:
            continue
        raw_file, raw_line = raw_location
        if not isinstance(raw_file, str) or isinstance(raw_line, bool):
            continue
        try:
            line = int(raw_line)
        except (TypeError, ValueError):
            continue
        if line <= 0:
            continue
        # Converting both slash forms before pathlib basename handling also
        # protects consumers when saved results came from another OS.
        filename = _string(Path(raw_file.replace("\\", "/")).name, 255)
        if not filename:
            continue
        normalized[kind] = {"file": filename, "line": line}
        if len(normalized) == 12:
            break
    return normalized


def _plugin(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    required = {
        "id", "name", "dir", "version", "kinds", "grade", "score",
        "observed", "composition", "firstParty", "baseline", "added",
        "evidence", "status",
    }
    if not required.issubset(row):
        return None
    plugin_id = _string(row.get("id"), 200)
    name = _string(row.get("name"), 200)
    version = _string(row.get("version"), 100)
    status = _string(row.get("status"), 32)
    grade = _string(row.get("grade"), 8).upper()
    score = row.get("score")
    kinds = row.get("kinds")
    observed = row.get("observed")
    added = row.get("added")
    composition = row.get("composition")
    evidence = row.get("evidence")
    if (
        not plugin_id or not name or not version
        or not isinstance(row.get("dir"), str)
        or not row["dir"].strip()
        or status not in VALID_STATUSES
        or grade not in VALID_GRADES
        or isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not math.isfinite(float(score))
        or not 0 <= float(score) <= 100
        or not isinstance(row.get("firstParty"), bool)
        or not isinstance(kinds, list) or not kinds
        or not all(isinstance(item, str) and item.strip() for item in kinds)
        or not isinstance(observed, list)
        or not all(isinstance(item, str) and item.strip() for item in observed)
        or row.get("baseline") is not None and not isinstance(row.get("baseline"), dict)
        or not isinstance(added, list)
        or not all(isinstance(item, str) and item.strip() for item in added)
        or not isinstance(composition, list)
        or not all(isinstance(item, str) and item.strip() for item in composition)
        or not isinstance(evidence, dict)
    ):
        return None
    for kind, location in evidence.items():
        if (
            not isinstance(kind, str) or not kind.strip()
            or not isinstance(location, (list, tuple)) or len(location) != 2
            or not isinstance(location[0], str) or not location[0].strip()
            or isinstance(location[1], bool) or not isinstance(location[1], int)
            or location[1] <= 0
        ):
            return None
    normalized_added_all = [_string(item, 300) for item in added]
    if len(set(normalized_added_all)) != len(normalized_added_all):
        return None
    normalized_added = normalized_added_all[:12]
    normalized_evidence_all = _evidence(evidence)
    normalized_evidence = {
        kind: normalized_evidence_all[kind]
        for kind in normalized_added
        if kind in normalized_evidence_all
    }
    if status in {"unchanged", "not-tracked"} and (added or evidence):
        return None
    if status == "changed" and not added:
        return None
    if any(_string(kind, 200) not in normalized_added_all for kind in evidence):
        return None
    return {
        "id": plugin_id,
        "name": name,
        "version": version,
        "grade": grade,
        "score": _score(score),
        "status": status,
        "firstParty": row["firstParty"],
        "added": normalized_added,
        "composition": _string_list(composition, 6),
        "evidence": normalized_evidence,
    }


def build_status(results: Any, scanned_at: datetime | None = None) -> dict[str, Any]:
    """Validate and normalize an Omaudit check result list."""
    if not isinstance(results, list):
        raise ValueError("Omaudit JSON top level must be a list")

    plugins: list[dict[str, Any]] = []
    plugin_ids: set[str] = set()
    for row in results:
        item = _plugin(row)
        if item is None:
            raise ValueError("Omaudit JSON contains an invalid plugin row")
        if item["id"] in plugin_ids:
            raise ValueError("Omaudit JSON contains duplicate plugin IDs")
        plugin_ids.add(item["id"])
        plugins.append(item)
    plugins.sort(
        key=lambda item: (
            STATUS_ORDER[item["status"]],
            GRADE_ORDER[item["grade"]],
            item["id"],
        )
    )
    changed = sum(item["status"] == "changed" for item in plugins)
    not_tracked = sum(item["status"] == "not-tracked" for item in plugins)
    unchanged = sum(item["status"] == "unchanged" for item in plugins)
    composition_risks = sum(bool(item["composition"]) for item in plugins)
    grades = [item["grade"] for item in plugins if item["grade"]]
    worst_grade = min(grades, key=GRADE_ORDER.__getitem__) if grades else ""
    visible_plugins = plugins[:MAX_PLUGINS]

    if changed:
        status_text = f"{changed} plugin{'s' if changed != 1 else ''} changed"
    elif not_tracked:
        noun = "plugin needs" if not_tracked == 1 else "plugins need"
        status_text = f"{not_tracked} {noun} baseline"
    elif plugins:
        status_text = "All tracked plugins unchanged"
    else:
        status_text = "No plugins found"

    return {
        "schemaVersion": 1,
        "ok": True,
        "installed": True,
        "scannedAt": _utc_seconds(scanned_at),
        "statusText": status_text,
        "worstGrade": worst_grade,
        "totals": {
            "plugins": len(plugins),
            "unchanged": unchanged,
            "changed": changed,
            "notTracked": not_tracked,
            "compositionRisks": composition_risks,
        },
        "plugins": visible_plugins,
        "error": "",
    }


def run_omaudit(include_builtins: bool = False) -> Any:
    """Run Omaudit using a fixed argv and decode its JSON output."""
    command = [*COMMAND]
    if include_builtins:
        command.append("--all")
    completed = _run_process_bounded(command, timeout=120)
    if completed.returncode not in (0, 1):
        raise OmauditError(f"Omaudit exited with unexpected exit code {completed.returncode}")
    try:
        results = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise OmauditError("Omaudit returned malformed JSON") from exc
    if not isinstance(results, list):
        raise OmauditError("Omaudit JSON top level must be a list")
    has_changed = any(
        isinstance(row, dict) and row.get("status") == "changed"
        for row in results
    )
    if completed.returncode == 0 and has_changed:
        raise OmauditError("Omaudit protocol mismatch: changed result with exit code 0")
    if completed.returncode == 1 and not has_changed:
        raise OmauditError("Omaudit protocol mismatch: exit code 1 without changed results")
    return results


def _error_status(installed: bool, message: str) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "ok": False,
        "installed": installed,
        "scannedAt": _utc_seconds(),
        "statusText": "Scan failed" if installed else "Omaudit not installed",
        "worstGrade": "",
        "totals": {
            "plugins": 0,
            "unchanged": 0,
            "changed": 0,
            "notTracked": 0,
            "compositionRisks": 0,
        },
        "plugins": [],
        "error": _string(message, 300),
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Emit normalized Omaudit status JSON")
    parser.add_argument("--input", metavar="FILE", help="read saved Omaudit check JSON")
    parser.add_argument(
        "--include-builtins",
        action="store_true",
        help="include first-party Omarchy plugins in addition to user plugins",
    )
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    try:
        if args.input:
            try:
                raw = _read_saved_output(args.input)
            except (OSError, UnicodeError) as exc:
                raise OmauditError("Unable to read saved Omaudit JSON") from exc
            try:
                results = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise OmauditError("Saved Omaudit output contains malformed JSON") from exc
        else:
            results = run_omaudit(args.include_builtins)
        document = build_status(results)
    except FileNotFoundError:
        document = _error_status(False, "Omaudit executable was not found")
    except subprocess.TimeoutExpired:
        document = _error_status(True, "Omaudit scan timed out after 120 seconds")
    except (OmauditError, ValueError) as exc:
        document = _error_status(True, str(exc))
    except OSError:
        document = _error_status(True, "Unable to run Omaudit")
    except Exception:
        document = _error_status(True, "Unexpected adapter failure")

    # ASCII-safe JSON prevents a multibyte UTF-8 code point from being split
    # across Quickshell's arbitrary streaming read boundaries.
    print(json.dumps(document, ensure_ascii=True, separators=(",", ":")))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
