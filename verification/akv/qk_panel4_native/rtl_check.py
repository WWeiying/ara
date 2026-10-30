"""Strict score transcript checker against the independent host oracle artifact."""
import json
from pathlib import Path
import re
import struct


def check_output(text, cases, golden):
    if len(cases) != 8 or len(golden) != 8 * 6 * 64 * 4:
        raise ValueError("Bad oracle geometry")
    lines = [line for line in text.splitlines() if line.startswith("RTL_QK_")]
    expected = ["RTL_QK_CAP native=1 panel4=1 pairs=8"]
    for case in cases:
        i, vl = case["id"], case["vl"]
        for mode in (0, 1):
            expected.append(f"RTL_QK_BEGIN case={i} mode={mode} kvhead={case['head']} "
                            f"tile={case['tile']} vl={vl} stride={case['stride']}")
            for row in range(6):
                values = struct.unpack_from("<" + "I" * vl, golden, (i * 384 + row * 64) * 4)
                expected.append(f"RTL_QK_ROW case={i} mode={mode} row={row} count={vl} bits=" +
                                "".join(f"{v:08x}" for v in values))
            expected.append(f"RTL_QK_END case={i} mode={mode} outputs={6*vl} "
                            f"tailwords={6*(64-vl)} guardbytes=512 inputbytes=34688 "
                            f"fcsr={case['fcsr']} vcsr=5 errors=0")
    expected.append("RTL_QK_SUITE_PASS pairs=8 runs=16 outputs=3240 tailwords=2904")
    if lines != expected:
        index = next((i for i, pair in enumerate(zip(lines, expected)) if pair[0] != pair[1]),
                     min(len(lines), len(expected)))
        raise ValueError(f"Missing/incorrect/duplicate score evidence at record {index}")
    if re.search(r"\b(?:FAIL|FAILED|FATAL|TIMEOUT)\b|Core Test \*\*\* FAILURE", text, re.I):
        raise ValueError("Failure in simulator transcript")
    if len(re.findall(r"Core Test \*\*\* SUCCESS", text)) != 1:
        raise ValueError("Require exactly one SoC success terminal")
    return dict(state="PASS", pairs=8, runs=16, outputs=3240, tailwords=2904,
                scope="score-only, not whole-Attention or performance")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--build", type=Path, required=True)
    p.add_argument("--log", type=Path, required=True)
    a = p.parse_args()
    import hashlib
    receipt = json.loads((a.build / "build.json").read_text())
    for path, digest in receipt["artifact_sha256"].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError("Build artifact drift: " + path)
    pins = json.loads((a.build / "source-pins.json").read_text())
    if hashlib.sha256((a.build / "source-pins.json").read_bytes()).hexdigest() != receipt["source_pins_sha256"]:
        raise ValueError("Source manifest drift")
    for path, digest in pins.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError("Source/tool drift: " + path)
    print(json.dumps(check_output(a.log.read_text(), receipt["cases"],
                                  (a.build / "golden.bin").read_bytes()), sort_keys=True))
