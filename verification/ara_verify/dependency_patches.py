"""Pinned local RTL deltas on top of the Bender dependency revisions.

Only a clean locked checkout or the exact reviewed working tree is accepted.
Nothing in this module resets local changes or imports a source tree's edits.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


class PatchError(RuntimeError):
    pass


DIFF_ARGS = (
    "diff", "--binary", "--full-index", "--no-ext-diff", "--no-textconv",
    "--no-renames", "--no-color", "--diff-algorithm=myers",
    "--no-indent-heuristic", "--unified=3", "--src-prefix=a/",
    "--dst-prefix=b/", "--ignore-submodules=all", "HEAD", "--",
)
REQUIRED_SUBMODULES = {
    "cva6": ("core/cache_subsystem/hpdcache", "core/cvfpu"),
}


def git(path: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-c", "core.quotePath=true", "-C", str(path), *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        raise PatchError(f"{path}: git {' '.join(args[:3])}: "
                         f"{result.stderr.decode(errors='replace').strip()}")
    return result.stdout


def canonical_diff(dependency: Path) -> bytes:
    # HEAD, not the index: staged edits must not disappear from the baseline.
    return git(dependency, *DIFF_ARGS)


def load_registry(root: Path) -> dict:
    directory = root / "verification/patches"
    try:
        data = json.loads((directory / "dependencies.json").read_text())
    except (OSError, ValueError) as error:
        raise PatchError(f"cannot read dependency patch registry: {error}") from error
    if data.get("schema_version") != 1 or not isinstance(data.get("patches"), dict):
        raise PatchError("invalid dependency patch registry schema")
    for name, spec in data["patches"].items():
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", name) or not isinstance(spec, dict):
            raise PatchError(f"invalid patch entry: {name}")
        if not re.fullmatch(r"[0-9a-f]{40}", spec.get("revision", "")):
            raise PatchError(f"{name}: invalid patch base revision")
        patch = Path(spec.get("patch", ""))
        if len(patch.parts) != 1 or patch.suffix != ".patch":
            raise PatchError(f"{name}: patch must be a local .patch filename")
        path = directory / patch
        if path.is_symlink() or not path.is_file():
            raise PatchError(f"{name}: missing or linked patch: {path}")
        content = path.read_bytes()
        if not content or hashlib.sha256(content).hexdigest() != spec.get("sha256"):
            raise PatchError(f"{name}: dependency patch digest mismatch")
    return data["patches"]


def _checkout(dependency: Path, revision: str) -> None:
    if dependency.is_symlink() or not (dependency / ".git").exists():
        raise PatchError(f"dependency must be a separate Git checkout: {dependency}")
    actual = git(dependency, "rev-parse", "HEAD").decode().strip()
    if actual != revision:
        raise PatchError(f"{dependency}: expected {revision}, found {actual}")
    untracked = git(dependency, "ls-files", "--others", "--exclude-standard", "-z")
    if untracked:
        raise PatchError(f"{dependency}: untracked input {untracked.split(bytes([0]))[0]!r}")
    # Unbuilt optional CVA6 submodules may be present; never import their local
    # HEADs as RTL patches. Parent gitlink edits are not approved, however.
    head_links = {}
    for record in git(dependency, "ls-tree", "-rz", "HEAD").split(b"\0"):
        if not record:
            continue
        metadata, relative = record.split(b"\t", 1)
        if metadata.startswith(b"160000 "):
            head_links[relative] = metadata.split()[2]
    index_links = {}
    for record in git(dependency, "ls-files", "--stage", "-z").split(b"\0"):
        if not record:
            continue
        metadata, relative = record.split(b"\t", 1)
        mode, oid, stage = metadata.split()
        if mode == b"160000":
            if stage != b"0":
                raise PatchError(f"{dependency}: unmerged index gitlink {relative!r}")
            index_links[relative] = oid
    if index_links != head_links:
        raise PatchError(f"{dependency}: added, removed or changed index gitlinks")


def patch_state(root: Path, package: str, dependency: Path, expected_revision: str) -> str:
    registry = load_registry(root)
    _checkout(dependency, expected_revision)
    actual = canonical_diff(dependency)
    spec = registry.get(package)
    if spec is None:
        if actual or git(dependency, "diff", "--cached", "--name-only", "HEAD"):
            raise PatchError(f"{package}: unapproved local changes")
        return "clean"
    if spec["revision"] != expected_revision:
        raise PatchError(f"{package}: patch base does not match Bender.lock")
    approved = (root / "verification/patches" / spec["patch"]).read_bytes()
    if actual == approved:
        # Reject hidden staged changes outside the approved working-tree delta.
        staged = set(git(dependency, "diff", "--cached", "--name-only", "-z", "HEAD").split(b"\0")) - {b""}
        changed = set(git(dependency, "diff", "--name-only", "-z", "HEAD").split(b"\0")) - {b""}
        unstaged = set(git(dependency, "diff", "--name-only", "-z").split(b"\0")) - {b""}
        if staged - changed:
            raise PatchError(f"{package}: hidden staged changes outside the patch")
        if staged & unstaged:
            raise PatchError(f"{package}: mixed staged/unstaged contents in approved files")
        return "applied"
    if not actual and not git(dependency, "diff", "--cached", "--name-only", "HEAD"):
        return "missing"
    raise PatchError(f"{package}: local changes differ from the approved patch")


def apply_patch_bundle(root: Path, package: str, dependency: Path, expected_revision: str) -> str:
    state = patch_state(root, package, dependency, expected_revision)
    if state == "missing":
        spec = load_registry(root)[package]
        path = root / "verification/patches" / spec["patch"]
        git(dependency, "apply", "--check", str(path))
        git(dependency, "apply", str(path))
        state = patch_state(root, package, dependency, expected_revision)
        if state != "applied":
            raise PatchError(f"{package}: patch application did not produce the pinned tree")
    return state


def _submodules(dependency: Path, package: str, allow_missing: bool) -> list[str]:
    missing = []
    for relative in REQUIRED_SUBMODULES.get(package, ()):
        record = git(dependency, "ls-tree", "HEAD", "--", relative).decode().strip()
        fields = record.split()
        if len(fields) != 4 or fields[:2] != ["160000", "commit"]:
            raise PatchError(f"{relative}: missing HEAD gitlink")
        expected = fields[2]
        index = git(dependency, "ls-files", "--stage", "--", relative).decode().split()
        if index != ["160000", expected, "0", relative]:
            raise PatchError(f"{relative}: index gitlink differs from HEAD")
        path = dependency / relative
        if path.is_symlink():
            raise PatchError(f"{relative}: linked submodule is not isolated")
        if not (path / ".git").exists():
            if path.exists() and (not path.is_dir() or any(path.iterdir())):
                raise PatchError(f"{relative}: refusing to replace a non-checkout path")
            if allow_missing:
                missing.append(relative)
                continue
            raise PatchError(f"{relative}: required submodule is not initialized")
        actual = git(path, "rev-parse", "HEAD").decode().strip()
        if actual != expected:
            raise PatchError(f"{relative}: expected {expected}, found {actual}")
        if git(path, "status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none"):
            raise PatchError(f"{relative}: dirty required submodule")
    return missing


def validate_submodules(dependency: Path, package: str) -> None:
    _submodules(dependency, package, allow_missing=False)


def ensure_submodules(dependency: Path, package: str) -> None:
    # Validate every existing checkout before materializing any missing one.
    missing = _submodules(dependency, package, allow_missing=True)
    if missing:
        git(dependency, "submodule", "update", "--init", "--checkout", "--", *missing)
    validate_submodules(dependency, package)


def snapshot(root: Path, package: str, source: Path) -> str:
    from .dependencies import locked_dependencies

    locked = {item.name: item for item in locked_dependencies(root / "Bender.lock")}
    if package not in locked:
        raise PatchError(f"unlocked dependency: {package}")
    revision = locked[package].revision
    destination = root / "hardware/deps" / package
    if destination.is_symlink():
        raise PatchError(f"refusing to modify a linked dependency: {destination}")
    if not destination.exists():
        # Clone the object database, never the source working tree; checkout the
        # lock revision even when the source has advanced since the last run.
        git(source, "cat-file", "-e", f"{revision}^{{commit}}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(["git", "clone", "--no-local", "--no-hardlinks",
                                 "--no-checkout", str(source), str(destination)], check=False)
        if result.returncode:
            raise PatchError(f"clone failed: {package}")
        git(destination, "checkout", "--detach", revision)
    # Refuse unknown local state before any nested checkout or patch change.
    patch_state(root, package, destination, revision)
    ensure_submodules(destination, package)
    return apply_patch_bundle(root, package, destination, revision)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(f"{args.package}: {snapshot(args.root.resolve(), args.package, args.source.resolve())}")
    except PatchError as error:
        parser.exit(1, f"error: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
