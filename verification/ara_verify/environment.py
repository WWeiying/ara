from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .dependencies import DependencyError, LockedTool, locked_tools
from .model import CheckResult


def _make_value(path: Path, variable: str) -> Optional[str]:
    pattern = re.compile(rf"^\s*{re.escape(variable)}\s*(?::|\?)?=\s*([^#]+)")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            return match.group(1).strip()
    return None


def config_values(repo_root: Path, config: str) -> Dict[str, int]:
    path = repo_root / "config" / f"{config}.mk"
    if not path.is_file():
        raise ValueError(f"configuration does not exist: {path}")
    values: Dict[str, int] = {}
    for key in ("nr_lanes", "vlen"):
        raw = _make_value(path, key)
        if raw is None:
            raise ValueError(f"{path}: missing {key}")
        try:
            values[key] = int(raw, 0)
        except ValueError as error:
            raise ValueError(f"{path}: invalid {key}: {raw}") from error
    return values


def resolve_bender(repo_root: Path) -> Optional[Path]:
    candidates: List[Path] = []
    if os.environ.get("ARA_BENDER"):
        candidates.append(Path(os.environ["ARA_BENDER"]))
    candidates.append(repo_root / "hardware" / "bender")
    configured = _make_value(repo_root / "hardware" / "Makefile", "BENDER")
    if configured:
        candidates.append(Path(configured))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
    return None


def bender_lock_revision(path: Path, package: str) -> Optional[str]:
    if not path.is_file():
        return None
    package_pattern = re.compile(rf"^  {re.escape(package)}:\s*$")
    revision_pattern = re.compile(r"^    revision:\s*([0-9a-fA-F]+)\s*$")
    in_package = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if package_pattern.match(line):
            in_package = True
            continue
        if in_package and line.startswith("  ") and not line.startswith("    "):
            break
        if in_package:
            match = revision_pattern.match(line)
            if match:
                return match.group(1).lower()
    return None


def _git_output(path: Path, *args: str) -> Optional[str]:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _command_output(command: List[str]) -> Optional[str]:
    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _dependency_check(repo_root: Path, package: str) -> List[CheckResult]:
    dependency = repo_root / "hardware" / "deps" / package
    if not dependency.is_dir():
        return [CheckResult("ERROR", f"{package} revision", f"missing: {dependency}")]

    expected = bender_lock_revision(repo_root / "Bender.lock", package)
    actual = _git_output(dependency, "rev-parse", "HEAD")
    if expected is None:
        revision = CheckResult("ERROR", f"{package} revision", "missing from Bender.lock")
    elif actual is None:
        revision = CheckResult("ERROR", f"{package} revision", "dependency is not a Git checkout")
    elif actual.lower() != expected:
        revision = CheckResult(
            "ERROR", f"{package} revision", f"expected {expected}, found {actual.lower()}"
        )
    else:
        revision = CheckResult("OK", f"{package} revision", actual.lower())

    status = _git_output(dependency, "status", "--porcelain=v1", "--ignore-submodules=none")
    if status is None:
        cleanliness = CheckResult("ERROR", f"{package} worktree", "cannot read Git status")
    elif status:
        first = status.splitlines()[0]
        cleanliness = CheckResult("ERROR", f"{package} worktree", f"dirty: {first}")
    else:
        cleanliness = CheckResult("OK", f"{package} worktree", "clean")
    return [revision, cleanliness]


def _tool_check(repo_root: Path, tool: LockedTool) -> List[CheckResult]:
    path = repo_root / tool.path
    if not path.is_dir():
        return [CheckResult("ERROR", f"tool:{tool.name}", f"missing: {path}")]

    actual = _git_output(path, "rev-parse", "HEAD")
    if actual is None:
        revision = CheckResult("ERROR", f"tool:{tool.name} revision", "not a Git checkout")
    elif actual.lower() != tool.revision:
        revision = CheckResult(
            "ERROR", f"tool:{tool.name} revision", f"expected {tool.revision}, found {actual.lower()}"
        )
    else:
        revision = CheckResult("OK", f"tool:{tool.name} revision", actual.lower())

    status = _git_output(path, "status", "--porcelain=v1", "--ignore-submodules=none")
    if status is None:
        cleanliness = CheckResult("ERROR", f"tool:{tool.name} worktree", "cannot read Git status")
    elif status:
        cleanliness = CheckResult(
            "ERROR", f"tool:{tool.name} worktree", f"dirty: {status.splitlines()[0]}"
        )
    else:
        cleanliness = CheckResult("OK", f"tool:{tool.name} worktree", "clean")

    rvv_source = path / "src" / "isa" / "rv32v_instr.sv"
    if tool.name == "riscv-dv-rvv1":
        source = rvv_source.read_text(encoding="utf-8") if rvv_source.is_file() else ""
        required = ("VSETIVLI", "VFREDUSUM_VS", "VCPOP_M")
        missing = [marker for marker in required if marker not in source]
        semantics = CheckResult(
            "ERROR" if missing else "OK",
            "riscv-dv RVV semantics",
            f"missing {', '.join(missing)}" if missing else "RVV 1.0 instruction model detected",
        )
        return [revision, cleanliness, semantics]
    return [revision, cleanliness]


def _path_check(name: str, path: Path) -> CheckResult:
    if path.exists():
        return CheckResult("OK", name, str(path.resolve()))
    return CheckResult("ERROR", name, f"missing: {path}")


def doctor(repo_root: Path, config: str, require_vcs: bool = True) -> List[CheckResult]:
    checks: List[CheckResult] = []
    checks.append(_path_check("LLVM toolchain", repo_root / "install/riscv-llvm/bin/clang"))
    checks.append(_path_check("GCC toolchain", repo_root / "install/riscv-gcc/bin/riscv64-unknown-elf-gcc"))
    checks.append(_path_check("application dependencies", repo_root / "apps/third-party"))
    for package in (
        "apb",
        "axi",
        "common_cells",
        "common_verification",
        "cva6",
        "fpnew",
        "fpu_div_sqrt_mvp",
        "tech_cells_generic",
    ):
        checks.extend(_dependency_check(repo_root, package))

    try:
        for tool in locked_tools(repo_root / "verification" / "toolchain.lock.json"):
            checks.extend(_tool_check(repo_root, tool))
    except DependencyError as error:
        checks.append(CheckResult("ERROR", "verification tool lock", str(error)))

    for command in ("git", "make"):
        executable = shutil.which(command)
        level = "OK" if executable else "ERROR"
        checks.append(CheckResult(level, command, executable or "not found in PATH"))
    if require_vcs:
        executable = shutil.which("vcs")
        checks.append(CheckResult("OK" if executable else "ERROR", "VCS", executable or "not found in PATH"))

    bender = resolve_bender(repo_root)
    if bender is None:
        checks.append(CheckResult("ERROR", "Bender", "not found"))
    else:
        expected_version = _make_value(repo_root / "hardware/Makefile", "BENDER_VERSION")
        output = _command_output([str(bender), "--version"])
        actual_version = output.split()[-1] if output else None
        if expected_version is None:
            checks.append(CheckResult("ERROR", "Bender", "BENDER_VERSION is not configured"))
        elif actual_version != expected_version:
            checks.append(CheckResult(
                "ERROR",
                "Bender",
                f"expected {expected_version}, found {actual_version or 'unknown'} at {bender}",
            ))
        else:
            checks.append(CheckResult("OK", "Bender", f"{actual_version} at {bender}"))

    try:
        values = config_values(repo_root, config)
        checks.append(CheckResult("OK", f"config/{config}.mk", f"lanes={values['nr_lanes']}, VLEN={values['vlen']}"))
    except ValueError as error:
        checks.append(CheckResult("ERROR", f"config/{config}.mk", str(error)))

    for path in sorted((repo_root / "config").glob("*_lanes.mk")):
        match = re.fullmatch(r"(\d+)_lanes", path.stem)
        if not match:
            continue
        raw = _make_value(path, "nr_lanes")
        if raw is not None and raw.isdigit() and int(raw) != int(match.group(1)):
            checks.append(CheckResult(
                "WARN",
                path.name,
                f"filename says {match.group(1)} lanes but nr_lanes={raw}",
            ))
    return checks


def has_errors(checks: Iterable[CheckResult]) -> bool:
    return any(check.level == "ERROR" for check in checks)
