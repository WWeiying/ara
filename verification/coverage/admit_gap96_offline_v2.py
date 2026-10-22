"""GAP96 successor: reject expected-pin replacement before strict admission."""
import json
from pathlib import Path

import admit_fp64_scan as admission


OUT = admission.ROOT / "verification/out"
PRE = OUT / "gap96-div32-pack-preflight-704-20261006-01/preflight-manifest.json"
PRE_SEAL = "841ae88618b17e8dcd2cea52da9d6cc9781887d78fb2b58a4d8e17cf73212eb0"
RUN = OUT / "gap96-div32-pack-old-image-20261006-01"
BASE = OUT / "gap95-offline-admitted-20261006-01"
original_sha, original_save = admission.sha, admission.save
wrapper = Path(__file__).resolve()
wrapper_sha = original_sha(wrapper)
shared_source = Path(admission.__file__).resolve()
shared_sha = original_sha(shared_source)
expected_pins = {}


def merge_expected(pins, additions):
    for path, expected in additions.items():
        admission.require(path not in pins or pins[path] == expected, "Expected-pin conflict: " + path)
        pins[path] = expected


def checked_sha(path):
    admission.require(original_sha(wrapper) == wrapper_sha, "Successor source drift")
    admission.require(original_sha(shared_source) == shared_sha, "Shared admission source drift")
    actual = original_sha(path)
    expected = expected_pins.get(str(path))
    admission.require(expected is None or actual == expected, "Pinned evidence drift: " + str(path))
    return actual


def setup():
    admission.require(original_sha(PRE) == PRE_SEAL, "Rebound preflight changed")
    pre = json.loads(PRE.read_bytes())
    admission.require(pre["status"] == "GAP96_SPIKE_PREFLIGHT_REBOUND_RAW704_NOT_VCS" and
                      pre["baseline_tests"] == 704 and pre["case"] == "vgap96_div32_pack",
                      "Wrong rebound preflight")
    merge_expected(expected_pins, pre["pins"])
    merge_expected(expected_pins, {str(PRE): PRE_SEAL, str(wrapper): wrapper_sha,
                                  str(shared_source): shared_sha})
    # Verify the existing chain before reading any baseline expected-pin file.
    for path in list(expected_pins):
        checked_sha(Path(path))
    old = json.loads((BASE / "evidence-pins.json").read_bytes())
    manifest = json.loads((RUN / "manifest.json").read_bytes())
    merge_expected(expected_pins, old)
    merge_expected(expected_pins, manifest["pins"])
    for path in list(expected_pins):
        checked_sha(Path(path))
    admission.require(all(manifest["pins"].get(path) == value for path, value in pre["pins"].items()),
                      "Run omitted or replaced preflight evidence")
    admission.require(manifest["preflight"] == {key: pre[key] for key in
        ("case", "eew", "vl", "checks", "symbols", "expected_vector_instructions",
         "expected_vector_bytes", "baseline_tests", "target_unhit_count")}, "Wrong run contract")
    command = manifest["command"]
    admission.require(command[0] == str(OUT / "repaired-aligned-build-20260930-01/sim/simv") and
        "+PRELOAD=" + pre["input_elf"] in command and "+TESTCASE=vgap96_div32_pack" in command,
        "Wrong image/ELF/case")
    for path in (RUN / "manifest.json", RUN / "simulation-status.json"):
        merge_expected(expected_pins, {str(path): checked_sha(path)})
    admission.sha = checked_sha
    admission.save = save_with_definition
    admission.SPECS = {"gap96": dict(stem="gap96-div32-pack", base="gap95-offline-admitted",
        count=704, instructions=42, bytes=10752, checks=2758, signature=0x80002288)}


def save_with_definition(path, value):
    if path.name == "evidence-pins.json":
        value = dict(value)
        merge_expected(value, expected_pins)
        merge_expected(value, {str(wrapper): wrapper_sha})
    original_save(path, value)


if __name__ == "__main__":
    setup()
    admission.main()
