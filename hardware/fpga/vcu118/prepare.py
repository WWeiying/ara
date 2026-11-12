#!/usr/bin/env python3
"""Resolve the FPGA integration without changing the parent RTL or lockfile."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CACHE = HERE / ".cache"
CHESHIRE = "cd73fd892a09da8aa9ae03171c0338bd3873007c"
BOARD_PORT = "a315a828abb61cf3cb9f4419b910ebe6739b90bf"
BOARD_TREE = "e50dc11804226e0c5c37826bd52a77675d9471b1"
FPGA_TARGETS = ("rtl", "fpga", "xilinx", "vcu118", "synthesis", "vivado",
                "cv64a6_imafdcv_sv39", "exclude_first_pass_decoder")


def run(*args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs)


def checkout(name, revision, branch):
    dst = CACHE / name
    if not dst.exists():
        subprocess.run(["git", "init", str(dst)], check=True)
        subprocess.run(["git", "-C", str(dst), "remote", "add", "origin",
                        "https://github.com/pulp-platform/cheshire.git"], check=True)
        subprocess.run(["git", "-C", str(dst), "fetch", "--depth", "1", "origin", revision], check=True)
        subprocess.run(["git", "-C", str(dst), "checkout", "--detach", "FETCH_HEAD"], check=True)
    if run("git", "-C", str(dst), "rev-parse", "HEAD").strip() != revision:
        raise RuntimeError(f"Unexpected Cheshire revision in {dst}; refusing to reset it")
    return dst


def dependency_roots(dependency_root=None):
    sys.path.insert(0, str(ROOT / "verification"))
    from ara_verify.dependencies import locked_dependencies
    from ara_verify.dependency_patches import PatchError, patch_state, validate_submodules

    parent = (dependency_root or ROOT / "hardware/deps").resolve()
    roots = {}
    for dependency in locked_dependencies(ROOT / "Bender.lock"):
        path = parent / dependency.name
        state = patch_state(ROOT, dependency.name, path, dependency.revision)
        if state == "missing":
            raise PatchError(f"{dependency.name}: required registered patch is not applied")
        validate_submodules(path, dependency.name)
        roots[dependency.name] = path
    return roots


def prepare(download_board=True, dependency_root=None):
    checked_dependencies = dependency_roots(dependency_root)
    CACHE.mkdir(parents=True, exist_ok=True)
    soc = checkout("cheshire_ara", CHESHIRE, "mp/ara-pulpv2-os-rebase")
    checkout("cheshire_board", BOARD_PORT, "main")
    # Preserve the integration's pinned peripheral revisions. Updating all remote
    # packages would silently mix a new SoC API with this Ara-enabled integration.
    lock = yaml.safe_load(run("git", "-C", str(soc), "show", "HEAD:Bender.lock"))
    roots = {"ara": ROOT}
    roots.update(checked_dependencies)
    for name, path in roots.items():
        manifest = yaml.safe_load((path / "Bender.yml").read_text())
        lock["packages"][name] = {
            "revision": None, "version": None, "source": {"Path": str(path)},
            "dependencies": list(manifest.get("dependencies", {})),
        }
    (soc / "Bender.lock").write_text(yaml.safe_dump(lock, sort_keys=False))
    (soc / "Bender.local").write_text(yaml.safe_dump({
        "overrides": {n: {"path": str(p)} for n, p in roots.items()}
    }))
    cmd = [str(ROOT / "hardware/bender"), "-d", str(soc), "sources", "-f"]
    for target in FPGA_TARGETS:
        cmd += ["-t", target]
    result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, text=True)
    groups = json.loads(result.stdout)
    (CACHE / "sources.json").write_text(json.dumps(groups, indent=2))
    package_names = list(lock["packages"])
    paths = run(str(ROOT / "hardware/bender"), "-d", str(soc), "path",
                *package_names).splitlines()
    if len(package_names) != len(paths):
        raise RuntimeError("Unexpected Bender path output")
    roots = dict(zip(package_names, paths))
    roots["cheshire"] = str(soc)
    (CACHE / "roots.json").write_text(json.dumps(roots, indent=2))

    if not download_board:
        print(f"Resolved {len(groups)} source groups; reusing pinned board files")
        return

    board = CACHE / "board_files" / "vcu118" / "2.4"
    board.mkdir(parents=True, exist_ok=True)
    api = "https://api.github.com/repos/Xilinx/XilinxBoardStore/git/"
    with urllib.request.urlopen(api + "trees/" + BOARD_TREE, timeout=60) as response:
        entries = json.load(response)["tree"]
    import base64
    import hashlib
    for entry in entries:
        if entry["type"] != "blob" or "/" in entry["path"]:
            raise RuntimeError("Unexpected board directory layout")
        dst = board / entry["path"]
        if dst.exists():
            data = dst.read_bytes()
            digest = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
            if digest == entry["sha"]:
                continue
        with urllib.request.urlopen(api + "blobs/" + entry["sha"], timeout=60) as response:
            blob = json.load(response)
        data = base64.b64decode(blob["content"])
        digest = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
        if digest != entry["sha"]:
            raise RuntimeError("Board source hash mismatch")
        dst.write_bytes(data)
    print(f"Resolved {len(groups)} source groups; pinned VCU118 board files ready")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dependency-root", type=Path,
                        help="Locked dependency checkouts with registered patches only")
    args = parser.parse_args()
    prepare(dependency_root=args.dependency_root)
