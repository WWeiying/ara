"""Read-only static source/model/artifact review; no producer execution or raw parse."""
import hashlib
import itertools
import json
from pathlib import Path
import re
import struct
import time

ROOT = Path(__file__).resolve().parent.parent
PREP = ROOT / "full482_optimized_prepare01"
WORK = PREP / "work05"


def read(path):
    return json.loads(path.read_text())


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def main():
    started = time.monotonic()
    ready = read(WORK / "READY.json")
    assert sha(WORK / "READY.json") == "06197d69f8e3767e358b0dacdb6020147f8b1dcf7c9961fd20f5929436a0941a"
    pins = {}
    for path, key in ((WORK / "READY.json", "pins"), (WORK / "PRE_REFERENCE.json", "pins"),
                      (PREP / "input_pins.json", None), (ROOT / "identity02/report.json", "input_pins")):
        data = read(path)
        for name, digest in (data[key] if key else data).items():
            assert name not in pins or pins[name] == digest, name
            pins[name] = digest
    for name, digest in pins.items():
        assert sha(Path(name)) == digest, name
    original = (WORK / "prepared03/original_prefix.c").read_text()
    current = (WORK / "prepared03/case.c").read_text()
    def rng_slice(source):
        return source[source.index("    for(unsigned seed="):source.index("        for(unsigned op=")]
    assert rng_slice(original) == rng_slice(current)
    assert (WORK / "prepared03/original_prefix.c").read_bytes() == (
        ROOT / "prepared02/prepared/macc_disjoint_e8_m4_prefix482/case.c").read_bytes()
    model = read(WORK / "model.json")
    rng, a, b = 0x937ad68de41c725f, [], []
    mask64 = (1 << 64) - 1
    for i in range(512):
        rng = (rng ^ (rng << 13)) & mask64
        rng ^= rng >> 7
        rng = (rng ^ (rng << 17)) & mask64
        x, y = rng & 255, (rng >> 19) & 255
        if i % 8 == 0: x, y = 0, 0
        elif i % 8 == 1: x, y = 255, 1
        elif i % 8 == 2: x, y = 128, 255
        elif i % 8 == 3: y = 8
        a.append(x); b.append(y)
    b[0] = 0
    assert (a, b) == (model["a"], model["b"])
    patterns = [[(0, 255, 128, 170 if i % 2 else 85,
                  (0x937ad68de41c725f + 0x9e3779b97f4a7c15 * i) & 255)[p]
                 for i in range(512)] for p in range(5)]
    masks = []
    for mode in range(4):
        bits = [mode == 0 or mode == 1 and i % 2 == 1 or mode == 2 and i % 7 == 2 for i in range(512)]
        masks.append([sum(int(bits[k*8+j]) << j for j in range(8)) for k in range(64)] + [0]*64)
    assert patterns == model["patterns"] and masks == model["masks"]
    tuples = []
    for vl, accumulator, mode in itertools.product((0,1,2,3,256,511,512),range(5),range(4)):
        tuples.extend((vl,accumulator,mode,start) for start in (1,vl//2,vl,511))
    tuples = tuples[:482]
    reference = read(WORK / "reference/status.json")
    capture = bytearray()
    old_expected = read(ROOT / "prepared02/expected_inputs.json")
    for n, ((vl, accumulator, mode, start), row, actual, old) in enumerate(
            zip(tuples, model["rows"], reference["calls"], old_expected)):
        assert (row["trial"],row["seed"],row["op"],row["vl"],row["accumulator"],row["mode"],row["vstart"],row["rm"]) == (n,0,0,vl,accumulator,mode,start,0)
        assert {k:row[k] for k in old} == old
        assert (actual["trial"],actual["vl"],actual["accumulator"],actual["mode"],actual["vstart"]) == (n,vl,accumulator,mode,start)
        out = [((patterns[accumulator][i] + a[i]*b[i]) & 255)
               if start <= i < vl and masks[mode][i//8] >> (i%8) & 1 else patterns[accumulator][i]
               for i in range(512)]
        assert row["old"] == patterns[accumulator] and row["output"] == out
        capture.extend(struct.pack("<7Q",n,0,vl,512,start,0,accumulator))
        capture.extend(bytes(a+b+masks[mode]+[91]+patterns[accumulator]+[91]+[91]+out+[91]))
    assert len(model["rows"]) == len(reference["calls"]) == len(old_expected) == 482
    for label in ("original","optimized"):
        assert (WORK / "host" / (label+".bin")).read_bytes() == capture
    table = (WORK / "prepared03/tables.h").read_text()
    rows_by_name = {"prefix_inputs":[a,b], "prefix_masks":masks,
                   "prefix_initial":[[91]+p+[91] for p in patterns],
                   "prefix_expected":[[91]+r["output"]+[91] for r in model["rows"]]}
    for name, rows in rows_by_name.items():
        section = re.search(r"static const uint64_t "+name+r"\[\d+\]\[\d+\] = \{(.*?)\n\};",table,re.S).group(1)
        words = [int(x,16) for x in re.findall(r"UINT64_C\(0x([0-9a-f]+)\)",section)]
        expected = []
        for row in rows:
            raw = bytes(row) + bytes((-len(row)) % 8)
            expected.extend(int.from_bytes(raw[i:i+8],"little") for i in range(0,len(raw),8))
        assert words == expected, name
    host = read(WORK / "host/status.json")
    assert host["expected_failures"] == 10 and len(host["mutations"]) == 11
    for mutation in host["mutations"]:
        want = 0 if mutation["name"] == "unused_after_guard_permission" else 1
        assert mutation["actual_result"] == want
        assert all(x["actual_returncode"] == want and x["retries"] == 0 for x in mutation["executions"])
    original_elf = (ROOT / "identity02/rvv_integer_macc_accumulators_restart_e8_m4").read_bytes()
    for backend, program in ready["programs"].items():
        binary = Path(program["path"]).read_bytes()
        assert hashlib.sha256(binary).hexdigest() == program["sha256"]
        routine = program["original13_routine"]
        encoded = b"".join(int(x["insn"],16).to_bytes(len(x["insn"])//2,"little") for x in routine)
        assert len(routine) == 13 and binary.count(encoded) == original_elf.count(encoded) == 1
        assert program["actual_compile"]["actual_returncode"] == 0
        mem = program["memory"]
        assert mem["bss_end"] < mem["stack_top"]-65536 < 0x80100000
        assert mem["conservative_sum_all_C_frames"] < 65536
    assert sha(WORK / "reference/status.json") == ready["reference_sha256"]
    assert reference["actual_execution"] == read(WORK / "reference/execution.json")
    assert reference["actual_execution"]["actual_child_returncode"] == 0
    assert reference["results"] == 246784 and reference["guards"] == 964
    assert reference["actual_helper_retire_counts"] == [482]*13
    assert reference["packed_output_reads"] == 31330 and reference["actual_HTIF_store_value"] == 1
    assert reference["minstret_to_replay_exit"] == 835145 == reference["raw_firmware_retired_to_exit_entry"] + reference["boot_retired"]
    print(json.dumps(dict(status="STATIC_SOURCE_MODEL_EVIDENCE_NO_BLOCKER_NOT_DUT_ENTRY",
        ready_sha256=sha(WORK/"READY.json"),auditor_sha256=sha(Path(__file__)),
        verified_pin_count=len(pins),calls=482,results=246784,guards=964,
        helper_instructions=6266,host_capture_bytes=len(capture),
        host_capture_sha256=hashlib.sha256(capture).hexdigest(),
        reference_sha256=sha(WORK/"reference/status.json"),
        no_Spike_Host_build_or_DUT_executed=True,raw_trace_parses=0,
        raw_bytes_hashed_only=True,elapsed_s=time.monotonic()-started),indent=2))


if __name__ == "__main__":
    main()
