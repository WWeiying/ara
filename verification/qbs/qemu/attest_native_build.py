#!/usr/bin/env python3
"""Incrementally build a QBS QEMU and bind its executable to audited sources."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    args = parser.parse_args()
    build = args.build.resolve()
    source = build.parent / "qemu-10.2.0"
    root = Path(__file__).resolve().parents[3]
    receipt = build / "native-model-manifest.json"
    if receipt.exists():
        raise RuntimeError("Use an unattested build; preserve an existing receipt")
    for name, relative in (("qbs_abi.h", "apps/common/qbs_abi.h"), ("qbs_ref.c", "verification/qbs/qbs_ref.c")):
        if sha(source / "target/riscv" / name) != sha(root / relative):
            raise RuntimeError(f"QEMU source differs: {name}")
    files = sorted(p for p in source.rglob("*") if p.is_file() and
                   (p.suffix in {".c", ".h", ".inc", ".decode", ".py", ".build", ".txt"}
                    or p.name in {"configure", "meson.build", "meson_options.txt", ".xaraqbs-source"}))
    files += [build / "build.ninja", build / "config-host.mak", Path(__file__).resolve()]
    before = {str(p): sha(p) for p in files}
    with (build / "native-model-build.log").open("wb") as log:
        subprocess.run(["ninja", "-C", str(build), "-j8", "qemu-system-riscv64"],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    if any(sha(Path(p)) != digest for p, digest in before.items()):
        raise RuntimeError("QEMU sources/configuration changed during attestation")
    executable = build / "qemu-system-riscv64"
    manifest = {"state": "PASS", "executable": str(executable), "executable_sha256": sha(executable),
                "source_sha256": before, "build_log_sha256": sha(build / "native-model-build.log")}
    receipt.write_text(json.dumps(manifest, indent=2) + "\n")
    print(receipt)


if __name__ == "__main__":
    main()
