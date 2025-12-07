#!/usr/bin/env python3
"""Arduino CLI build helper for the Christmas Tree LED controller firmware.

This script mirrors the Arduino IDE compile flow while remaining adaptive to
board or library changes. It relies on `arduino-cli` for dependency discovery
and compilation. Usage examples:

    python esp32/utils/arduino_build.py
    python esp32/utils/arduino_build.py --fqbn esp32:esp32:esp32 --clean

Prerequisites:
  * `arduino-cli` must be installed and available on PATH.
  * Required cores/libraries can be managed automatically if missing.

Environment configuration defaults to `arduino-cli.yaml` in the repository
root when present; otherwise the global Arduino CLI configuration is used.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import json
import platform
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any


FQBN_DEFAULT = (
    "esp32:esp32:esp32:"
    "UploadSpeed=921600,CPUFreq=240,FlashMode=qio,FlashSize=4M,PartitionScheme=default,"
    "DebugLevel=none,PSRAM=disabled,EraseFlash=none"
)
CORE_PACKAGE_DELIMITER = ":"


class BuildError(RuntimeError):
    """Raised when the build or prerequisite checks fail."""


class TimingEntry:
    """Represents a single timing measurement with nested sub-operations."""

    def __init__(
        self,
        name: str,
        start_time: float,
        end_time: float | None = None,
        sub_operations: list[TimingEntry] | None = None,
        command: str | None = None,
        output_size: int | None = None,
        network_activity: bool = False,
        status: str | None = None,
        redundancy: str | None = None,
        output_snippet: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.start_time = start_time
        self.end_time = end_time
        self.duration = (end_time - start_time) if end_time else None
        self.sub_operations = sub_operations or []
        self.command = command
        self.output_size = output_size
        self.network_activity = network_activity
        self.status = status
        self.redundancy = redundancy
        self.output_snippet = output_snippet
        self.metadata = metadata or {}

    def format_duration(self) -> str:
        """Format duration as seconds with 3 decimal precision."""
        if self.duration is None:
            return "N/A"
        return f"{self.duration:.3f}s"


class TimingLogger:
    """Logs timing information for build operations to a structured log file."""

    def __init__(self, log_file: Path, enable_file_logging: bool = False) -> None:
        self.log_file = log_file
        self.enable_file_logging = enable_file_logging
        self.entries: list[TimingEntry] = []
        self.session_start: float = time.time()
        self.session_context: dict[str, Any] = {}

    def set_context(self, **kwargs: Any) -> None:
        """Set session context information."""
        self.session_context.update(kwargs)

    @contextlib.contextmanager
    def time_operation(
        self,
        name: str,
        command: str | None = None,
        phase: str | None = None,
    ) -> Iterator[TimingEntry]:
        """Context manager to time an operation."""
        start = time.time()
        entry = TimingEntry(name, start, command=command)
        if phase:
            entry.metadata["phase"] = phase

        try:
            yield entry
            entry.end_time = time.time()
            entry.duration = entry.end_time - entry.start_time
            self.entries.append(entry)
        except Exception:
            entry.end_time = time.time()
            entry.duration = entry.end_time - entry.start_time
            entry.status = "ERROR"
            self.entries.append(entry)
            raise

    def analyze_redundancy(self, stdout: str, stderr: str) -> tuple[str | None, str | None]:
        """Analyze command output to detect redundant operations."""
        combined = (stdout + " " + stderr).lower()
        redundancy = None
        output_snippet = None

        # Check for already installed messages
        if "already installed" in combined:
            if "platform" in combined or "core" in combined:
                redundancy = "REDUNDANT_CHECK (core already installed, could skip update-index)"
            else:
                redundancy = "REDUNDANT_CHECK (library already installed)"
            # Extract the "already installed" message
            for line in (stdout + stderr).splitlines():
                if "already installed" in line.lower():
                    output_snippet = line.strip()
                    break

        # Check for index downloads
        if "downloading index" in combined or "downloaded" in combined:
            if "package_index" in combined:
                redundancy = "REDUNDANT_NETWORK_OPERATION (index downloaded every run, not cached)"
                for line in (stdout + stderr).splitlines():
                    if "index" in line.lower() and "download" in line.lower():
                        output_snippet = line.strip()
                        break

        # Check for skipped installs
        if "skipped" in combined or "skip" in combined:
            if not redundancy:
                redundancy = "REDUNDANT_CHECK (operation skipped)"

        return redundancy, output_snippet

    def detect_network_activity(self, duration: float, output_size: int) -> bool:
        """Heuristically detect network activity based on duration and output size."""
        # Commands taking >1s with significant output likely involve network I/O
        return duration > 1.0 and output_size > 1000

    def log_command(
        self,
        name: str,
        command: str,
        duration: float,
        stdout: str = "",
        stderr: str = "",
        status: str | None = None,
    ) -> TimingEntry:
        """Log a command execution with analysis."""
        output_size = len(stdout.encode("utf-8")) + len(stderr.encode("utf-8"))
        network_activity = self.detect_network_activity(duration, output_size)
        redundancy, output_snippet = self.analyze_redundancy(stdout, stderr)

        entry = TimingEntry(
            name,
            time.time() - duration,
            time.time(),
            command=command,
            output_size=output_size,
            network_activity=network_activity,
            status=status or ("SKIPPED" if redundancy and "REDUNDANT_CHECK" in redundancy else None),
            redundancy=redundancy,
            output_snippet=output_snippet,
        )
        return entry

    def write_log(self) -> None:
        """Write all timing entries to the log file in structured format."""
        if not self.enable_file_logging:
            return  # File logging disabled, but keep all data in memory for potential future use

        session_end = time.time()
        total_duration = session_end - self.session_start

        with self.log_file.open("a", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write("BUILD SESSION START\n")
            f.write(f"Timestamp: {datetime.datetime.fromtimestamp(self.session_start, tz=datetime.timezone.utc).isoformat()}\n")
            f.write(f"Python Version: {sys.version.split()[0]}\n")
            f.write(f"Platform: {platform.system()} {platform.release()}\n")

            for key, value in self.session_context.items():
                f.write(f"{key}: {value}\n")

            # Group entries by phase
            phases: dict[str, list[TimingEntry]] = {}
            unphased: list[TimingEntry] = []

            for entry in self.entries:
                phase = entry.metadata.get("phase", "UNKNOWN")
                if phase == "UNKNOWN":
                    unphased.append(entry)
                else:
                    if phase not in phases:
                        phases[phase] = []
                    phases[phase].append(entry)

            # Write each phase
            phase_order = ["INITIALIZATION", "CONFIGURATION", "CORE_MANAGEMENT", "LIBRARY_MANAGEMENT", "COMPILATION", "FIRMWARE_PROCESSING"]
            for phase_name in phase_order:
                if phase_name in phases:
                    self._write_phase(f, phase_name, phases[phase_name])

            # Write unphased entries
            if unphased:
                self._write_phase(f, "OTHER", unphased)

            # Write summary
            f.write("=" * 80 + "\n")
            f.write("BUILD SESSION SUMMARY\n")
            f.write(f"Total Duration: {total_duration:.3f}s\n")
            f.write("Breakdown by Phase:\n")

            phase_totals: dict[str, float] = {}
            network_ops = 0
            files_created = []

            for entry in self.entries:
                phase = entry.metadata.get("phase", "OTHER")
                if entry.duration:
                    phase_totals[phase] = phase_totals.get(phase, 0) + entry.duration
                if entry.network_activity:
                    network_ops += 1
                if entry.metadata.get("file_created"):
                    files_created.append(entry.metadata["file_created"])

            for phase_name in phase_order:
                if phase_name in phase_totals:
                    phase_duration = phase_totals[phase_name]
                    percentage = (phase_duration / total_duration * 100) if total_duration > 0 else 0
                    f.write(f"  - {phase_name.replace('_', ' ').title()}: {phase_duration:.3f}s ({percentage:.2f}%)\n")

            if phase_totals.get("OTHER", 0) > 0:
                other_duration = phase_totals["OTHER"]
                percentage = (other_duration / total_duration * 100) if total_duration > 0 else 0
                f.write(f"  - Other: {other_duration:.3f}s ({percentage:.2f}%)\n")

            f.write(f"Network Operations: {network_ops} detected\n")
            if files_created:
                f.write(f"Files Created: {len(files_created)} binary(ies) ({', '.join(files_created)})\n")
            f.write("=" * 80 + "\n\n")

    def _write_phase(self, f: Any, phase_name: str, entries: list[TimingEntry]) -> None:
        """Write entries for a specific phase."""
        f.write("=" * 80 + "\n")
        f.write(f"PHASE: {phase_name.replace('_', ' ').upper()}\n")

        for entry in entries:
            start_iso = datetime.datetime.fromtimestamp(entry.start_time, tz=datetime.timezone.utc).isoformat()
            f.write(f"- Operation: {entry.name}\n")
            f.write(f"  Start: {start_iso}\n")
            f.write(f"  Duration: {entry.format_duration()}\n")

            if entry.command:
                f.write(f"  Command: {' '.join(entry.command) if isinstance(entry.command, list) else entry.command}\n")

            if entry.sub_operations:
                f.write("  Sub-operations:\n")
                for sub in entry.sub_operations:
                    f.write(f"    - {sub.name}\n")
                    if sub.command:
                        f.write(f"      Command: {' '.join(sub.command) if isinstance(sub.command, list) else sub.command}\n")
                    f.write(f"      Duration: {sub.format_duration()}\n")
                    if sub.output_size is not None:
                        f.write(f"      Output Size: {sub.output_size} bytes\n")
                    f.write(f"      Network Activity: {'Yes' if sub.network_activity else 'No'}\n")
                    if sub.status:
                        f.write(f"      Status: {sub.status}\n")
                    if sub.redundancy:
                        f.write(f"      Redundancy: {sub.redundancy}\n")
                    if sub.output_snippet:
                        f.write(f"      Output Snippet: \"{sub.output_snippet}\"\n")
                    if sub.metadata:
                        for key, value in sub.metadata.items():
                            if key != "phase":
                                f.write(f"      {key.replace('_', ' ').title()}: {value}\n")

            if entry.output_size is not None:
                f.write(f"  Output Size: {entry.output_size} bytes\n")
            f.write(f"  Network Activity: {'Yes' if entry.network_activity else 'No'}\n")
            if entry.status:
                f.write(f"  Status: {entry.status}\n")
            if entry.redundancy:
                f.write(f"  Redundancy: {entry.redundancy}\n")
            if entry.output_snippet:
                f.write(f"  Output Snippet: \"{entry.output_snippet}\"\n")
            if entry.metadata:
                for key, value in entry.metadata.items():
                    if key not in ("phase", "file_created"):
                        f.write(f"  {key.replace('_', ' ').title()}: {value}\n")
            if entry.status or entry.redundancy:
                result_text = entry.status if entry.status else "Success"
                if entry.redundancy and "REDUNDANT_CHECK" in entry.redundancy:
                    if "already installed" in (entry.output_snippet or "").lower():
                        result_text = "Verified (already present)"
                    else:
                        result_text = "Skipped"
                f.write(f"  Result: {result_text}\n")


def find_repo_root(script_path: Path) -> Path:
    # Script is at esp32/utils/arduino_build.py
    # parents[0] = esp32/utils/
    # parents[1] = esp32/
    # parents[2] = repo root
    return script_path.resolve().parents[2]


class CacheManager:
    """Manages caching of arduino-cli list results.

    Provides caching for installed cores and libraries to reduce network calls.
    Cache expiration is configurable - longer expiration reduces network overhead
    during active development. Cache is automatically invalidated when dependencies
    are installed/uninstalled, ensuring data freshness.

    Manual invalidation available via --force-refresh flag or invalidate() method.
    """

    def __init__(self, cache_dir: Path, expiration_seconds: int = 300) -> None:
        """Initialize CacheManager with specified cache directory and expiration time.

        Args:
            cache_dir: Directory to store cache files
            expiration_seconds: Cache expiration time in seconds. Default 300 (5 minutes).
                               For static dependencies like installed cores/libraries,
                               longer expiration (e.g., 2629800 = ~1 month) reduces
                               unnecessary network calls during active development.
                               Cache is automatically invalidated when dependencies
                               change (install/uninstall), providing safety.
        """
        self.cache_dir = cache_dir
        self.expiration_seconds = expiration_seconds
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_cache_path(self, cache_type: str) -> Path:
        """Get path to cache file for given type (core_list, lib_list)."""
        return self.cache_dir / f"{cache_type}.json"

    def is_cache_valid(self, cache_path: Path) -> bool:
        """Check if cache file exists and is not expired."""
        if not cache_path.exists():
            return False
        age = time.time() - cache_path.stat().st_mtime
        return age < self.expiration_seconds

    def load_cache(self, cache_type: str) -> dict[str, Any] | None:
        """Load cached data if valid, otherwise return None."""
        cache_path = self.get_cache_path(cache_type)
        if not self.is_cache_valid(cache_path):
            return None
        try:
            with cache_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def get_cache_info(self, cache_type: str) -> dict[str, Any]:
        """Get detailed cache information for debugging."""
        cache_path = self.get_cache_path(cache_type)
        info: dict[str, Any] = {
            "cache_path": str(cache_path),
            "exists": cache_path.exists(),
        }

        if cache_path.exists():
            stat = cache_path.stat()
            age = time.time() - stat.st_mtime
            info["age_seconds"] = age
            info["expiration_seconds"] = self.expiration_seconds
            info["is_expired"] = age >= self.expiration_seconds
            info["file_size"] = stat.st_size

            # Try to load and inspect structure
            try:
                with cache_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    info["structure_valid"] = isinstance(data, dict)
                    if isinstance(data, dict):
                        info["has_installed_key"] = "installed" in data
                        if "installed" in data:
                            installed_val = data.get("installed")
                            info["installed_is_list"] = isinstance(installed_val, list)
                            if isinstance(installed_val, list):
                                info["installed_count"] = len(installed_val)
                                info["installed_sample"] = installed_val[:3] if installed_val else []
            except (json.JSONDecodeError, OSError) as e:
                info["load_error"] = str(e)
        else:
            info["age_seconds"] = None
            info["expiration_seconds"] = self.expiration_seconds
            info["is_expired"] = None

        return info

    def save_cache(self, cache_type: str, data: dict[str, Any]) -> None:
        """Save data to cache file."""
        cache_path = self.get_cache_path(cache_type)
        try:
            with cache_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass  # Silently fail if cache can't be written

    def invalidate(self, cache_type: str | None = None) -> None:
        """Invalidate cache file(s). If cache_type is None, invalidate all."""
        if cache_type:
            cache_path = self.get_cache_path(cache_type)
            if cache_path.exists():
                cache_path.unlink()
        else:
            # Invalidate all caches
            for cache_file in self.cache_dir.glob("*.json"):
                cache_file.unlink()


def ensure_arduino_cli() -> Path:
    cli_path = shutil.which("arduino-cli")
    if not cli_path:
        raise BuildError(
            "arduino-cli not found in PATH. Install it from https://arduino.github.io/arduino-cli "
            "and ensure the executable is available."
        )
    return Path(cli_path)


# Global logger instance (set in main())
_logger: TimingLogger | None = None

# Global cache manager instance (set in main())
_cache_manager: CacheManager | None = None


def run_cli(
    cli_path: Path,
    args: list[str],
    *,
    capture: bool = False,
    log_name: str | None = None,
    parent_entry: TimingEntry | None = None,
    verbose: bool = True,
) -> subprocess.CompletedProcess:
    """Run arduino-cli command with optional timing instrumentation."""
    cmd = [str(cli_path), *args]
    cmd_str = " ".join(cmd)
    start_time = time.time()

    # Print command info if verbose and we have a log name
    if verbose and log_name:
        print(f"→ {log_name}...", flush=True)

    try:
        # If verbose, show output in real-time instead of capturing
        should_capture = capture or (_logger is not None and not verbose)
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=should_capture,
            text=True,
        )
        duration = time.time() - start_time

        # If verbose and we captured, print output
        if verbose and should_capture:
            if result.stdout:
                print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)

        # Log the command if logger is available (but don't write to file if disabled)
        if _logger is not None:
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            command_entry = _logger.log_command(
                log_name or cmd_str,
                cmd_str,
                duration,
                stdout=stdout,
                stderr=stderr,
            )
            if parent_entry:
                parent_entry.sub_operations.append(command_entry)
            else:
                _logger.entries.append(command_entry)

        # Print completion message if verbose
        if verbose and log_name:
            print(f"✓ {log_name} completed ({duration:.2f}s)", flush=True)

        return result
    except subprocess.CalledProcessError as exc:
        duration = time.time() - start_time
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""

        # Log failed command
        if _logger is not None:
            command_entry = _logger.log_command(
                log_name or cmd_str,
                cmd_str,
                duration,
                stdout=stdout,
                stderr=stderr,
                status="ERROR",
            )
            if parent_entry:
                parent_entry.sub_operations.append(command_entry)

        message_lines = [f"Command failed: {cmd_str}"]
        if stdout.strip():
            message_lines.append(f"stdout:\n{stdout}")
        if stderr.strip():
            message_lines.append(f"stderr:\n{stderr}")
        raise BuildError("\n".join(message_lines)) from exc


def ensure_core(cli_path: Path, fqbn: str, config_args: list[str], force_refresh: bool = False, verbose: bool = True) -> None:
    """Ensure required core is installed, with timing instrumentation and caching."""
    package = CORE_PACKAGE_DELIMITER.join(fqbn.split(CORE_PACKAGE_DELIMITER)[:2])

    def _check_and_install(entry: TimingEntry | None = None) -> None:
        use_cache = _cache_manager is not None and not force_refresh
        installed: set[str] = set()
        cache_valid = False

        # STEP 1: Try to load from cache first (Cache-First Pattern)
        if use_cache:
            # Get detailed cache info for debugging
            cache_info = _cache_manager.get_cache_info("core_list")
            if entry:
                entry.metadata["cache_info"] = cache_info

            cached_data = _cache_manager.load_cache("core_list")
            if cached_data and isinstance(cached_data, dict) and "installed" in cached_data:
                cached_installed = cached_data.get("installed", [])
                # Explicit verification: only set cache_valid if we have actual data structure
                if isinstance(cached_installed, list):
                    installed = set(cached_installed)
                    cache_valid = True
                    if entry:
                        entry.metadata["cache_used"] = True
                        entry.metadata["cache_entries_count"] = len(installed)
                        entry.metadata["cache_hit"] = True  # Explicit cache hit marker
                        entry.metadata["cache_state"] = "valid"
                        entry.metadata["package_in_cache"] = package in installed
            else:
                # Cache miss: cache not loaded or invalid structure
                if entry:
                    entry.metadata["cache_state"] = "invalid"
                    if not cached_data:
                        # Determine specific reason from cache_info
                        if not cache_info.get("exists"):
                            entry.metadata["cache_miss_reason"] = "cache_file_not_found"
                        elif cache_info.get("is_expired"):
                            entry.metadata["cache_miss_reason"] = f"cache_expired (age: {cache_info.get('age_seconds', 0):.0f}s, expiration: {cache_info.get('expiration_seconds', 0)}s)"
                        else:
                            entry.metadata["cache_miss_reason"] = "cache_load_failed"
                    else:
                        entry.metadata["cache_miss_reason"] = "invalid_structure"
                        if isinstance(cached_data, dict):
                            entry.metadata["cache_keys"] = list(cached_data.keys())
        else:
            # Cache disabled (force_refresh or no cache manager)
            if entry:
                entry.metadata["cache_state"] = "not_checked"
                if force_refresh:
                    entry.metadata["cache_miss_reason"] = "force_refresh"

        # STEP 2: Early return if core found in valid cache (Early Return Pattern)
        # Explicit verification: check BOTH cache_valid AND package presence
        if cache_valid and package in installed:
            if entry:
                entry.status = "Core already present (from cache)"
                entry.metadata["core_version"] = package
                entry.metadata["operations_skipped"] = ["core list", "update-index"]
                entry.metadata["early_return_reason"] = "cache_hit_and_package_found"
            return  # CRITICAL: Skip both core list AND update-index - never run below

        # STEP 3: Only query arduino-cli if cache miss/expired (Progressive Fallback)
        # Defensive guard: ONLY run if cache is definitely invalid
        if not cache_valid:
            # Runtime verification: if cache was marked as hit, log error
            if entry and entry.metadata.get("cache_hit"):
                entry.metadata["error"] = "Cache marked as hit but core list running - logic error!"

            # Log why we're running core list (for debugging)
            if entry:
                if "cache_miss_reason" not in entry.metadata:
                    entry.metadata["cache_miss_reason"] = "cache_not_valid"

            try:
                result = run_cli(
                    cli_path,
                    [*config_args, "core", "list", "--format", "json"],
                    capture=True,
                    log_name="List installed cores",
                    parent_entry=entry,
                )
            except BuildError as exc:
                raise BuildError(f"Unable to query installed cores: {exc}")

            # Parse and extract installed cores
            installed.clear()  # Reset before parsing (cache was invalid, so installed is empty anyway)
            try:
                parsed = json.loads(result.stdout)
            except json.JSONDecodeError:
                parsed = None

            if isinstance(parsed, list):
                items = parsed
            elif isinstance(parsed, dict):
                # Try "platforms" first (actual structure from arduino-cli)
                items = parsed.get("platforms")
                if items is None:
                    # Fall back to "installed" (for backward compatibility or cache format)
                    items = parsed.get("installed")
            else:
                items = None

            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        # Extract core ID from platform entry
                        core_id = item.get("ID") or item.get("id")
                        if core_id:
                            installed.add(core_id)

                # Debug logging for parsing
                if entry:
                    entry.metadata["json_items_count"] = len(items)
                    entry.metadata["installed_cores_after_parsing"] = list(installed)
                    entry.metadata["package_being_checked"] = package
                    entry.metadata["package_found_after_parsing"] = package in installed

            if not installed:
                # Fall back to parsing plain text output (one core per line).
                for line in result.stdout.splitlines():
                    token = line.strip().split()[0] if line.strip() else ""
                    if token.count(":") >= 1:
                        installed.add(token)

                if entry:
                    entry.metadata["used_plain_text_fallback"] = True
                    entry.metadata["installed_cores_after_fallback"] = list(installed)

            # Save to cache for future runs
            if use_cache:
                _cache_manager.save_cache("core_list", {"installed": list(installed)})
                if entry:
                    entry.metadata["cache_updated"] = True
                    entry.metadata["cache_saved_cores"] = list(installed)

        # STEP 4: Early return if core now found after query (Guard Clause)
        if package in installed:
            if entry:
                entry.status = "Core already present"
                entry.metadata["core_version"] = package
                entry.metadata["early_return_after_query"] = True
                entry.metadata["operations_skipped"] = ["update-index", "core install"]
            if verbose:
                print(f"✓ Core {package} already installed", flush=True)
            return  # Skip update-index since core is installed

        # STEP 5: Only run update-index and install if core is actually missing
        # (Conditional Command Execution)
        if entry:
            entry.metadata["core_missing"] = True
            entry.metadata["installed_cores_when_missing"] = list(installed)
        if verbose:
            print(f"Installing core {package}...", flush=True)
        run_cli(
            cli_path,
            [*config_args, "core", "update-index"],
            log_name="Update core index",
            parent_entry=entry,
            verbose=verbose,
        )
        # Always capture output to check if installation was skipped
        install_result = run_cli(
            cli_path,
            [*config_args, "core", "install", package],
            capture=True,  # Always capture to check for "already installed"
            log_name=f"Install core {package}",
            parent_entry=entry,
            verbose=verbose,
        )
        # Only invalidate cache if core was actually installed (not skipped)
        # Check if output indicates core was already installed (no actual installation)
        install_output = (install_result.stdout or "") + (install_result.stderr or "")
        actually_installed = "already installed" not in install_output.lower()

        if actually_installed:
            # Core was actually installed, invalidate cache
            if use_cache:
                _cache_manager.invalidate("core_list")
            if entry:
                entry.status = "Core installed"
                entry.metadata["cache_invalidated"] = True
        else:
            # Core was already installed, keep cache valid
            if entry:
                entry.status = "Core already installed (install skipped)"
                entry.metadata["install_skipped"] = True
                entry.metadata["cache_invalidated"] = False

    if _logger is not None:
        with _logger.time_operation(f"Ensure core {package}", phase="CORE_MANAGEMENT") as entry:
            _check_and_install(entry)
    else:
        _check_and_install()


def normalize_library_name(name: str) -> str:
    """Normalize library name for comparison (case-insensitive, whitespace-tolerant)."""
    # Convert to lowercase and normalize whitespace
    normalized = " ".join(name.lower().split())
    return normalized


def maybe_install_libraries(cli_path: Path, config_args: list[str], libraries: set[str], force_refresh: bool = False, verbose: bool = True) -> None:
    """Check and install missing libraries, with timing instrumentation and caching."""
    if not libraries:
        return

    def _check_and_install(entry: TimingEntry | None = None) -> None:
        installed: set[str] = set()
        installed_normalized: dict[str, str] = {}  # normalized -> original name
        use_cache = _cache_manager is not None and not force_refresh
        cache_valid = False  # Add cache validity tracking
        result = None

        # STEP 1: Try to load from cache first (Cache-First Pattern)
        if use_cache:
            cached_data = _cache_manager.load_cache("lib_list")
            if cached_data and isinstance(cached_data, dict):
                if "installed" in cached_data and "installed_normalized" in cached_data:
                    cached_installed = cached_data.get("installed")
                    cached_normalized = cached_data.get("installed_normalized")

                    # Validate types
                    if isinstance(cached_installed, list) and isinstance(cached_normalized, dict):
                        installed = set(cached_installed)
                        installed_normalized = {k: v for k, v in cached_normalized.items()}
                        cache_valid = True  # Explicit cache validity marker
                        if entry:
                            entry.metadata["cache_used"] = True
                            entry.metadata["cache_libraries_count"] = len(installed)
                            entry.metadata["cache_normalized_count"] = len(installed_normalized)
                            entry.metadata["cache_hit"] = True  # Explicit cache hit marker
                            entry.metadata["cache_state"] = "valid"
                            # Sample cache contents for debugging
                            if installed_normalized:
                                entry.metadata["cache_normalized_sample"] = {
                                    k: v for k, v in list(installed_normalized.items())[:3]
                                }
                    else:
                        # Invalid cache structure
                        if entry:
                            entry.metadata["cache_invalid"] = True
                            entry.metadata["cache_state"] = "invalid"
                            entry.metadata["cache_miss_reason"] = "invalid_structure"
                else:
                    # Cache missing required keys
                    if entry:
                        entry.metadata["cache_invalid_keys"] = True
                        entry.metadata["cache_state"] = "invalid"
                        entry.metadata["cache_miss_reason"] = "missing_keys"
            else:
                # Cache miss: cache not loaded or invalid structure
                if entry:
                    entry.metadata["cache_state"] = "invalid"
                    entry.metadata["cache_miss_reason"] = "cache_not_found_or_invalid" if not cached_data else "invalid_structure"
        else:
            # Cache disabled (force_refresh or no cache manager)
            if entry:
                entry.metadata["cache_state"] = "not_checked"
                if force_refresh:
                    entry.metadata["cache_miss_reason"] = "force_refresh"

        # STEP 2: Only query arduino-cli if cache miss/expired (Progressive Fallback)
        # Defensive guard: ONLY run if cache is definitely invalid
        if not cache_valid:
            # Runtime verification: if cache was marked as hit, log error
            if entry and entry.metadata.get("cache_hit"):
                entry.metadata["error"] = "Cache marked as hit but lib list running - logic error!"

            # Log why we're running lib list (for debugging)
            if entry:
                if "cache_miss_reason" not in entry.metadata:
                    entry.metadata["cache_miss_reason"] = "cache_not_valid"

            try:
                result = run_cli(
                    cli_path,
                    [*config_args, "lib", "list", "--format", "json"],
                    capture=True,
                    log_name="List installed libraries",
                    parent_entry=entry,
                )
            except BuildError:
                result = None

            if result is not None:
                try:
                    parsed = json.loads(result.stdout)
                except json.JSONDecodeError:
                    parsed = None

                items = None
                json_structure = "unknown"
                json_key_used = None

                if isinstance(parsed, dict):
                    # Handle actual JSON structure: {"installed_libraries": [...]}
                    items = parsed.get("installed_libraries")
                    if items is not None:
                        json_structure = "dict"
                        json_key_used = "installed_libraries"
                elif isinstance(parsed, list):
                    # Handle list format (backward compatibility)
                    items = parsed
                    json_structure = "list"

                if items is not None and isinstance(items, list):
                    for lib_entry in items:
                        if isinstance(lib_entry, dict):
                            lib = lib_entry.get("library")
                            if isinstance(lib, dict):
                                name = lib.get("name")
                                if name:
                                    installed.add(name)
                                    # Store normalized version for matching
                                    normalized = normalize_library_name(name)
                                    installed_normalized[normalized] = name

                # Log JSON parsing debug info
                if entry:
                    entry.metadata["json_structure"] = json_structure
                    entry.metadata["json_key_used"] = json_key_used
                    entry.metadata["libraries_extracted_count"] = len(installed)
                    entry.metadata["libraries_extracted_sample"] = list(installed)[:5]

            if not installed and result is not None:
                # Plain-text fallback: handle table format
                # Format: "Name                  Installed Available   Location Description"
                #         "Ethernet              2.0.2     -           user     -"
                for line in result.stdout.splitlines():
                    # Skip header line
                    if line.strip().startswith("Name") and "Installed" in line:
                        continue

                    # Extract library name from first column
                    # Library name is everything before the version number (first token that matches version pattern)
                    parts = line.strip().split()
                    if parts:
                        # Find where version starts (pattern: digits.digits or just text)
                        # Library name could be multiple words, so take everything before version
                        # Version typically starts with digits followed by dot
                        name_parts = []
                        for part in parts:
                            # If part looks like version (digits.digits), stop collecting name parts
                            if re.match(r'^\d+\.\d+', part):
                                break
                            name_parts.append(part)

                        if name_parts:
                            name = " ".join(name_parts)
                            if name:
                                installed.add(name)
                                normalized = normalize_library_name(name)
                                installed_normalized[normalized] = name

            # Save to cache for future runs (only if cache was invalid/missing)
            if use_cache and not cache_valid:
                _cache_manager.save_cache("lib_list", {
                    "installed": list(installed),
                    "installed_normalized": installed_normalized,
                })
                if entry:
                    entry.metadata["cache_updated"] = True

        # Normalize required libraries for comparison
        required_normalized: dict[str, str] = {}
        for lib in libraries:
            normalized = normalize_library_name(lib)
            required_normalized[normalized] = lib

        # Find missing libraries using normalized comparison
        missing = []
        found_libraries = []
        matching_debug = []

        for normalized_req, original_req in required_normalized.items():
            if normalized_req in installed_normalized:
                found_libraries.append(original_req)
                matching_debug.append(f"{normalized_req} -> {installed_normalized[normalized_req]} (MATCHED)")
            else:
                missing.append(original_req)
                matching_debug.append(f"{normalized_req} -> NOT FOUND")

        missing = sorted(missing)
        installed_count = 0

        if missing and verbose:
            library_word = "library" if len(missing) == 1 else "libraries"
            print(f"Installing {len(missing)} missing {library_word}...", flush=True)

        for lib in missing:
            run_cli(
                cli_path,
                [*config_args, "lib", "install", lib],
                log_name=f"Install library {lib}",
                parent_entry=entry,
                verbose=verbose,
            )
            installed_count += 1
            # Invalidate cache after installing a library
            if use_cache:
                _cache_manager.invalidate("lib_list")

        if verbose and not missing:
            print(f"✓ All {len(libraries)} required libraries already installed", flush=True)

        if entry:
            entry.metadata["libraries_checked"] = len(libraries)
            entry.metadata["libraries_missing"] = len(missing)
            entry.metadata["libraries_installed"] = installed_count
            entry.metadata["libraries_found"] = len(found_libraries)
            entry.metadata["libraries_found_list"] = found_libraries
            entry.metadata["libraries_missing_list"] = missing
            entry.metadata["required_normalized_all"] = list(required_normalized.keys())
            entry.metadata["matching_debug"] = matching_debug
            # Add normalization examples
            if installed_normalized:
                sample_normalized = {k: v for k, v in list(installed_normalized.items())[:3]}
                entry.metadata["normalized_sample"] = sample_normalized
            # Track if we used cache and skipped lib list
            if cache_valid and entry.metadata.get("cache_hit"):
                entry.metadata["operations_skipped"] = ["lib list"]
            if installed_count > 0:
                library_word = "library" if installed_count == 1 else "libraries"
                entry.status = f"{installed_count} {library_word} installed, {len(found_libraries)} already present"
            else:
                entry.status = f"All {len(libraries)} libraries already present"

    if _logger is not None:
        with _logger.time_operation("Check/Install libraries", phase="LIBRARY_MANAGEMENT") as entry:
            _check_and_install(entry)
    else:
        _check_and_install()


def compile_sketch(
    cli_path: Path,
    config_args: list[str],
    fqbn: str,
    sketch: Path,
    build_dir: Path,
    clean: bool,
    extra_libs: set[str],
    force_refresh: bool = False,
    verbose: bool = True,
) -> None:
    """Compile the sketch with timing instrumentation."""
    def _compile(entry: TimingEntry | None = None) -> None:
        if clean and build_dir.exists():
            if entry:
                entry.metadata["build_dir_cleaned"] = True
            if verbose:
                print("Cleaning build directory...", flush=True)
            shutil.rmtree(build_dir)

        build_dir.mkdir(parents=True, exist_ok=True)

        maybe_install_libraries(cli_path, config_args, extra_libs, force_refresh, verbose=verbose)

        compile_args = [
            *config_args,
            "compile",
            "--fqbn",
            fqbn,
            "--build-path",
            str(build_dir),
            str(sketch),
        ]

        if verbose:
            print("Compiling sketch...", flush=True)
        run_cli(
            cli_path,
            compile_args,
            log_name="Compile sketch",
            parent_entry=entry,
            verbose=verbose,
        )
        if entry:
            entry.status = "Success"

    if _logger is not None:
        with _logger.time_operation("Compile sketch", phase="COMPILATION") as entry:
            _compile(entry)
    else:
        _compile()


def detect_libraries(repo_root: Path) -> set[str]:
    """Detect required libraries from manifest file."""
    manifest = repo_root / "esp32" / "utils" / "required-libraries.txt"
    start_time = time.time()
    libraries = set()

    if manifest.exists():
        libraries = {
            line.strip()
            for line in manifest.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }

    if _logger is not None:
        entry = TimingEntry(
            "Detect required libraries",
            start_time,
            time.time(),
            metadata={"phase": "LIBRARY_MANAGEMENT", "libraries_found": list(libraries), "count": len(libraries)},
        )
        _logger.entries.append(entry)

    return libraries


def configure_network_timeouts(cli_path: Path, config_args: list[str], timeout_seconds: int = 600, verbose: bool = True) -> None:
    """Configure network timeouts with timing instrumentation."""
    value = f"{timeout_seconds}s"
    # Note: network.timeout is not a valid arduino-cli config key
    keys = [
        "network.connection_timeout",
    ]

    def _configure(entry: TimingEntry | None = None) -> None:
        for key in keys:
            try:
                run_cli(
                    cli_path,
                    [*config_args, "config", "set", key, value],
                    log_name=f"Set {key}",
                    parent_entry=entry,
                    verbose=verbose,
                )
            except BuildError as exc:
                print(f"Warning: unable to set {key}: {exc}", file=sys.stderr)
                if entry:
                    entry.metadata[f"{key}_error"] = str(exc)

    if _logger is not None:
        with _logger.time_operation("Configure network timeouts", phase="CONFIGURATION") as entry:
            _configure(entry)
    else:
        _configure()




def main() -> int:
    """Main entry point with full timing instrumentation."""
    global _logger, _cache_manager

    try:
        parser = argparse.ArgumentParser(description="Compile the Christmas Tree LED controller firmware using arduino-cli.")
        parser.add_argument("--fqbn", default=FQBN_DEFAULT, help="Fully qualified board name (default: %(default)s)")
        parser.add_argument(
            "--sketch",
            default=None,
            help="Path to the sketch (default: <repo>/esp32/xmas_tree.ino)",
        )
        parser.add_argument(
            "--build-dir",
            default=None,
            help="Output directory for build artifacts (default: <repo>/build/arduino)",
        )
        parser.add_argument("--clean", action="store_true", help="Remove the build directory before compiling")
        parser.add_argument(
            "--force-refresh",
            action="store_true",
            help="Force refresh of library/core cache (ignore cached results)",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Reduce output verbosity (less stdout output)",
        )
        parser.add_argument(
            "--enable-file-logging",
            action="store_true",
            help="Enable detailed logging to arduino_build.log file (disabled by default)",
        )
        args = parser.parse_args()

        verbose = not args.quiet
        enable_file_logging = args.enable_file_logging

        # Initialize logger
        script_path = Path(__file__).resolve()
        repo_root = find_repo_root(script_path)
        log_file = repo_root / "arduino_build.log"
        _logger = TimingLogger(log_file, enable_file_logging=enable_file_logging)

        if verbose and not enable_file_logging:
            print("Note: File logging disabled (use --enable-file-logging to enable)", flush=True)

        # Initialize cache manager with long expiration for static dependencies
        # Libraries and cores rarely change during development, so long cache duration
        # reduces unnecessary network calls. Cache is automatically invalidated when
        # cores/libraries are installed, providing safety. Use --force-refresh to
        # manually invalidate cache if needed.
        cache_dir = repo_root / ".arduino_cache"
        _cache_manager = CacheManager(cache_dir, expiration_seconds=2629800)  # ~1 month (30.44 days)

        # Instrument initialization phase
        with _logger.time_operation("Script initialization", phase="INITIALIZATION") as init_entry:
            sketch_path = Path(args.sketch) if args.sketch else repo_root / "esp32" / "xmas_tree.ino"
            if not sketch_path.exists():
                raise BuildError(f"Sketch not found: {sketch_path}")

            build_dir = Path(args.build_dir) if args.build_dir else repo_root / "build" / "arduino"
            init_entry.metadata["sketch"] = str(sketch_path)
            init_entry.metadata["build_dir"] = str(build_dir)
            init_entry.metadata["clean"] = args.clean

        with _logger.time_operation("Find arduino-cli", phase="INITIALIZATION") as cli_entry:
            cli_path = ensure_arduino_cli()
            cli_entry.metadata["cli_path"] = str(cli_path)
            cli_entry.status = f"Found at {cli_path}"

        # Get arduino-cli version
        with _logger.time_operation("Get arduino-cli version", phase="INITIALIZATION") as version_entry:
            try:
                version_result = run_cli(
                    cli_path,
                    ["version"],
                    capture=True,
                    log_name="Get arduino-cli version",
                    parent_entry=version_entry,
                )
                arduino_cli_version = version_result.stdout.strip()
                version_entry.metadata["version"] = arduino_cli_version
            except BuildError:
                arduino_cli_version = "Unknown"
                version_entry.status = "Failed to get version"

        config_file = repo_root / "arduino-cli.yaml"
        config_args: list[str] = ["--config-file", str(config_file)] if config_file.exists() else []

        # Set session context
        _logger.set_context(
            Arduino_CLI_Version=arduino_cli_version,
            FQBN=args.fqbn,
            Sketch=str(sketch_path),
            Build_Dir=str(build_dir),
            Clean=str(args.clean),
            Config_File=str(config_file) if config_file.exists() else "None (using global config)",
        )

        if verbose:
            print("Configuring network timeouts...", flush=True)
        configure_network_timeouts(cli_path, config_args, verbose=verbose)

        ensure_core(cli_path, args.fqbn, config_args, force_refresh=args.force_refresh, verbose=verbose)

        libraries_to_install = detect_libraries(repo_root)
        if verbose and libraries_to_install:
            library_word = "library" if len(libraries_to_install) == 1 else "libraries"
            print(f"Detected {len(libraries_to_install)} required {library_word}", flush=True)

        compile_sketch(
            cli_path,
            config_args,
            args.fqbn,
            sketch_path,
            build_dir,
            args.clean,
            libraries_to_install,
            force_refresh=args.force_refresh,
            verbose=verbose,
        )

        if verbose:
            print(f"\n✓ Build completed. Artifacts in {build_dir}", flush=True)

        # Write log file
        _logger.write_log()

        return 0
    except Exception:
        # Ensure log is written even on error
        if _logger:
            _logger.write_log()

        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BuildError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)

