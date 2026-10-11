#!/usr/bin/env python3
"""Reconstruct pinned RCE experiment dependencies in a new, private directory.

The checked-in manifest records upstream bases plus inherited local patches.
--cache may point to an existing dependency tree, used only as a Git object
source. No files, refs, submodules or configuration in that tree are changed.
Without --cache, fetch the fixed revisions from the manifest's repository URLs.
This script never replaces an existing dependency directory.
"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


HARDWARE = Path(__file__).resolve().parents[1]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inside(root, relative):
    """Reject absolute paths, escapes and symlink redirects in manifest paths."""
    path = root / relative
    if Path(relative).is_absolute() or path.resolve() != path.absolute():
        raise ValueError("Unsafe manifest path: " + relative)
    path.relative_to(root)
    return path


def git(directory, *args):
    return subprocess.run(
        ["git", "-C", str(directory), *args], check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        timeout=300,
    ).stdout.strip()


def verify(destination, manifest):
    for package in manifest["packages"]:
        path = inside(destination, package["path"])
        if git(path, "rev-parse", "HEAD") != package["revision"]:
            raise ValueError("Wrong dependency base: " + package["path"])
    for relative, expected in manifest["required_files_sha256"].items():
        path = inside(destination, relative)
        if sha256(path) != expected:
            raise ValueError("Dependency input differs: " + relative)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    manifest_path = HARDWARE / "reduction_deps/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["schema"] != 1:
        raise ValueError("Unsupported dependency snapshot schema")
    helper = HARDWARE / "scripts/prepare_reduction_dependency_overlay.py"
    if sha256(helper) != manifest["overlay_helper_sha256"]:
        raise ValueError("Build-time dependency repair changed; review the snapshot first")
    for package in manifest["packages"]:
        if package["patch"]:
            patch = inside(manifest_path.parent, package["patch"])
            if sha256(patch) != package["patch_sha256"]:
                raise ValueError("Dependency patch hash mismatch: " + package["patch"])
    if args.destination.is_symlink():
        raise ValueError("Destination must not be a symlink")
    destination = args.destination.absolute()
    # Resolve only the existing parent so a normal absolute/relative destination
    # is accepted while all later manifest paths stay under this owned root.
    destination = destination.parent.resolve() / destination.name
    if args.verify_only:
        verify(destination, manifest)
        print("Verified pinned dependency inputs:", destination)
        return
    if destination.exists():
        raise ValueError("Destination already exists; use --verify-only or a new directory")
    destination.mkdir(parents=True)
    record = {"manifest_sha256": sha256(manifest_path), "packages": [], "status": "preparing"}
    report = destination / "rce_dependency_snapshot.json"
    try:
        for package in manifest["packages"]:
            path = inside(destination, package["path"])
            path.mkdir(parents=True, exist_ok=True)
            if any(path.iterdir()):
                raise ValueError("Dependency destination is not empty: " + str(path))
            source = str((args.cache / package["path"]).resolve()) if args.cache else package["url"]
            print("Preparing", package["path"], package["revision"], flush=True)
            git(path, "init", "-q")
            git(path, "fetch", "--no-tags", "--depth=1", source, package["revision"])
            git(path, "checkout", "--detach", "-q", "FETCH_HEAD")
            if package["patch"]:
                patch = str(manifest_path.parent / package["patch"])
                git(path, "apply", "--check", patch)
                git(path, "apply", patch)
            record["packages"].append({"path": package["path"], "source": source,
                                       "revision": package["revision"]})
        verify(destination, manifest)
        # Copy this generated file into a fresh Ara checkout as Bender.local.
        # Path overrides cover transitive packages as well as direct ones, so
        # Bender does not silently resolve the historical lockfile revisions.
        overrides = {p["path"]: {"path": str(destination / p["path"])}
                     for p in manifest["packages"] if "/" not in p["path"]}
        (destination / "Bender.local").write_text(
            json.dumps({"overrides": overrides}, indent=2) + "\n")
        record["status"] = "verified"
        record["verified_files"] = len(manifest["required_files_sha256"])
    except Exception as error:
        record["status"] = "failed"
        record["error"] = str(error)
        if isinstance(error, subprocess.CalledProcessError):
            record["stderr"] = error.stderr
        raise
    finally:
        report.write_text(json.dumps(record, indent=2) + "\n")
    print("Verified", record["verified_files"], "dependency input files in", destination)


if __name__ == "__main__":
    main()
