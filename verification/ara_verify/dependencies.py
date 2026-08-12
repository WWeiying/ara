from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple


class DependencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class LockedDependency:
    name: str
    revision: str
    url: str


@dataclass(frozen=True)
class LockedTool:
    name: str
    revision: str
    url: str
    fetch_ref: str
    path: Path


def locked_dependencies(path: Path) -> List[LockedDependency]:
    if not path.is_file():
        raise DependencyError(f"lock file does not exist: {path}")

    package_re = re.compile(r"^  ([A-Za-z0-9_.-]+):\s*$")
    revision_re = re.compile(r"^    revision:\s*([0-9a-fA-F]+)\s*$")
    git_re = re.compile(r"^      Git:\s*(\S+)\s*$")
    dependencies: List[LockedDependency] = []
    name: Optional[str] = None
    revision: Optional[str] = None
    url: Optional[str] = None

    def finish() -> None:
        if name is None:
            return
        if revision is None or url is None:
            raise DependencyError(f"{path}: package {name} is not a locked Git dependency")
        dependencies.append(LockedDependency(name, revision.lower(), url))

    for line in path.read_text(encoding="utf-8").splitlines():
        package_match = package_re.match(line)
        if package_match:
            finish()
            name = package_match.group(1)
            revision = None
            url = None
            continue
        if name is None:
            continue
        revision_match = revision_re.match(line)
        if revision_match:
            revision = revision_match.group(1)
            continue
        git_match = git_re.match(line)
        if git_match:
            url = git_match.group(1)
    finish()

    if not dependencies:
        raise DependencyError(f"{path}: no locked Git dependencies found")
    return dependencies


def locked_tools(path: Path) -> List[LockedTool]:
    if not path.is_file():
        raise DependencyError(f"tool lock file does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise DependencyError(f"cannot parse tool lock file {path}: {error}") from error

    if data.get("schema_version") != 1 or not isinstance(data.get("tools"), dict):
        raise DependencyError(f"{path}: expected schema_version 1 and a tools object")

    tools: List[LockedTool] = []
    for name, spec in sorted(data["tools"].items()):
        if not isinstance(spec, dict):
            raise DependencyError(f"{path}: tool {name} must be an object")
        revision = spec.get("revision", "")
        url = spec.get("url", "")
        fetch_ref = spec.get("fetch_ref", "")
        tool_path = Path(spec.get("path", ""))
        if not re.fullmatch(r"[0-9a-fA-F]{40}", revision):
            raise DependencyError(f"{path}: tool {name} has an invalid revision")
        if not url or not fetch_ref:
            raise DependencyError(f"{path}: tool {name} requires url and fetch_ref")
        if not tool_path.parts or tool_path.is_absolute() or ".." in tool_path.parts:
            raise DependencyError(f"{path}: tool {name} path must be relative and stay within the repository")
        tools.append(LockedTool(name, revision.lower(), url, fetch_ref, tool_path))
    return tools


def _run(command: Sequence[str], cwd: Optional[Path] = None) -> None:
    result = subprocess.run(command, cwd=cwd, text=True, check=False)
    if result.returncode != 0:
        raise DependencyError(f"command failed ({result.returncode}): {' '.join(command)}")


def _git_output(path: Path, *args: str) -> Optional[str]:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _checkout_state(path: Path, name: str) -> Optional[str]:
    if not path.exists():
        return None
    if _git_output(path, "rev-parse", "--is-inside-work-tree") != "true":
        raise DependencyError(f"refusing to replace non-Git dependency path: {path}")
    status = _git_output(path, "status", "--porcelain=v1", "--ignore-submodules=none")
    if status is None:
        raise DependencyError(f"cannot read Git status: {path}")
    if status:
        raise DependencyError(f"refusing to overwrite dirty dependency {name}: {status.splitlines()[0]}")
    return _git_output(path, "rev-parse", "HEAD")


def _sync_locked_tool(repo_root: Path, tool: LockedTool, dry_run: bool) -> Tuple[str, str]:
    path = repo_root / tool.path
    actual = _checkout_state(path, tool.name)
    label = f"tool:{tool.name}"
    if actual == tool.revision:
        return label, "unchanged"
    if dry_run:
        return label, f"checkout {tool.revision}"

    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        _run(["git", "clone", "--no-checkout", tool.url, str(path)])
    _run(["git", "fetch", "--depth=1", "origin", tool.fetch_ref], cwd=path)
    _run(["git", "checkout", "--detach", tool.revision], cwd=path)
    actual = _git_output(path, "rev-parse", "HEAD")
    if actual != tool.revision:
        raise DependencyError(f"{tool.name}: expected {tool.revision}, found {actual or 'unknown'}")
    return label, f"checked out {tool.revision}"


def sync_dependencies(repo_root: Path, dry_run: bool = False) -> List[Tuple[str, str]]:
    dependency_root = repo_root / "hardware" / "deps"
    actions: List[Tuple[str, str]] = []

    for dependency in locked_dependencies(repo_root / "Bender.lock"):
        path = dependency_root / dependency.name
        actual = _checkout_state(path, dependency.name)

        if actual == dependency.revision:
            actions.append((dependency.name, "unchanged"))
            continue
        if dry_run:
            actions.append((dependency.name, f"checkout {dependency.revision}"))
            continue

        dependency_root.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            _run(["git", "clone", "--no-checkout", dependency.url, str(path)])
        _run(["git", "fetch", "--depth=1", dependency.url, dependency.revision], cwd=path)
        _run(["git", "checkout", "--detach", dependency.revision], cwd=path)
        actual = _git_output(path, "rev-parse", "HEAD")
        if actual != dependency.revision:
            raise DependencyError(
                f"{dependency.name}: expected {dependency.revision}, found {actual or 'unknown'}"
            )
        actions.append((dependency.name, f"checked out {dependency.revision}"))

    for tool in locked_tools(repo_root / "verification" / "toolchain.lock.json"):
        actions.append(_sync_locked_tool(repo_root, tool, dry_run))
    return actions
