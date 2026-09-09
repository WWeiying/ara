#!/usr/bin/env python3
"""Resolve the FPGA integration without changing the parent RTL or lockfile."""
import argparse
import json
from pathlib import Path
import subprocess
import urllib.request

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CACHE = HERE / ".cache"
CHESHIRE = "cd73fd892a09da8aa9ae03171c0338bd3873007c"
BOARD_PORT = "a315a828abb61cf3cb9f4419b910ebe6739b90bf"
BOARD_TREE = "e50dc11804226e0c5c37826bd52a77675d9471b1"


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


def prepare(download_board=True):
    CACHE.mkdir(parents=True, exist_ok=True)
    soc = checkout("cheshire_ara", CHESHIRE, "mp/ara-pulpv2-os-rebase")
    checkout("cheshire_board", BOARD_PORT, "main")
    # Preserve the integration's pinned peripheral revisions. Updating all remote
    # packages would silently mix a new SoC API with this Ara-enabled integration.
    lock = yaml.safe_load(run("git", "-C", str(soc), "show", "HEAD:Bender.lock"))
    roots = {"ara": ROOT}
    parent_lock = yaml.safe_load((ROOT / "Bender.lock").read_text())
    for name in parent_lock["packages"]:
        roots[name] = ROOT / "hardware" / "deps" / name
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
    for target in ["rtl", "fpga", "xilinx", "vcu118", "synthesis", "vivado",
                   "cv64a6_imafdcv_sv39", "exclude_first_pass_decoder"]:
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
    argparse.ArgumentParser(description=__doc__).parse_args()
    prepare()
