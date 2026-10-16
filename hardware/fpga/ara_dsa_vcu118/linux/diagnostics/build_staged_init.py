#!/usr/bin/env python3
"""Replace only init in a pinned rootfs with diagnostic stage markers."""
import argparse
import hashlib
from pathlib import Path
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("source", type=Path)
p.add_argument("output", type=Path)
a = p.parse_args()
archive = a.source.read_bytes()
if hashlib.sha256(archive).hexdigest() != "4c1f196a90cbba5cd73af81712c526067ab8e83efb7d303cbde829528f4e3b25":
    p.error("Wrong original rootfs")
a.output.mkdir(parents=True, exist_ok=False)
root = a.output / "root"
root.mkdir()
subprocess.run(["cpio", "-id", "--quiet", "--no-absolute-filenames", "--no-preserve-owner"],
               input=archive, cwd=root, check=True)
init = Path(__file__).with_name("staged_init.sh").read_bytes()
(root / "init").write_bytes(init)
(root / "init").chmod(0o755)
names = subprocess.check_output(["find", ".", "-print0"], cwd=root)
result = subprocess.check_output(["cpio", "--null", "--quiet", "-o", "-H", "newc", "--owner=0:0"],
                                 cwd=root, input=names)
if len(result) > len(archive):
    raise SystemExit("Diagnostic rootfs exceeds original initrd extent")
result += bytes(len(archive) - len(result))
path = a.output / "initramfs.cpio"
path.write_bytes(result)
print("DIAGNOSTIC_STAGE_MARKERS_NOT_LINUX_ACCEPTANCE", hashlib.sha256(result).hexdigest(), path)
