"""Reject a Resident SoC filelist that lost the registered CVA6 retirement fix."""
import argparse
import hashlib
import json
from pathlib import Path
import re


REGISTRY = Path(__file__).resolve().parents[3] / "verification/patches/dependencies.json"
TARGET = "core/commit_stage.sv"


def check(filelist, registry=REGISTRY):
    spec = json.loads(registry.read_text())["patches"]["cva6"]
    bundle = (registry.parent / spec["patch"]).read_bytes()
    if hashlib.sha256(bundle).hexdigest() != spec["sha256"]:
        raise ValueError("registered CVA6 patch digest mismatch")
    path = re.escape(TARGET)
    matches = re.findall(rf"^diff --git a/{path} b/{path}\nindex [0-9a-f]{{40}}\.\.([0-9a-f]{{40}})\b",
                         bundle.decode(), re.MULTILINE)
    if len(matches) != 1:
        raise ValueError("missing or ambiguous registered commit_stage post-image")
    sources = [Path(s) for raw in filelist.read_text().splitlines()
               if (s := raw.strip()) and not s.startswith(("#", "//", "+", "-"))
               and Path(s).parts[-2:] == ("core", "commit_stage.sv")]
    if len(sources) != 1 or not sources[0].is_absolute():
        raise ValueError(f"expected one absolute {TARGET} source in {filelist}; found {sources}")
    data = sources[0].read_bytes()
    # The patch's index line identifies a Git blob, not the bare file SHA-1.
    oid = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
    if oid != matches[0]:
        raise ValueError(f"{sources[0]}: got {oid}, expected registered {matches[0]}; "
                         "restore the retirement fix or register the reviewed replacement")
    return oid


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("filelist", type=Path)
    args = parser.parse_args()
    try:
        print("Resident CVA6 commit source verified:", check(args.filelist))
    except (OSError, ValueError, KeyError) as e:
        parser.exit(1, f"Resident CVA6 preflight failed: {e}\n")
