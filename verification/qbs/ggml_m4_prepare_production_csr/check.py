"""Strict direct-production-TU CSR log checker; no timing claims."""
import json
from pathlib import Path
import re
import sys

BLOCKS = ([1] * 5 + [2, 17, 28, 32, 33] + [2] * 21 +
          [1 + i % 3 for i in range(32)] + [1] * 4 + [2] * 6 + [1, 0, 28])
ELIGIBLE = set(range(63)) | {64, 73, 75}
SEEDS = (0, 8, 31)
FNV_OFFSET = 14695981039346656037
FNV_PRIME = 1099511628211


def require(ok, message):
    if not ok:
        raise ValueError(message)


def fields(line, label, names):
    words = line.split()
    require(words[0] == label, "Wrong record label")
    result = {}
    for word in words[1:]:
        key, sep, value = word.partition("=")
        require(sep and key and value and key not in result, "Malformed/duplicate field")
        result[key] = value
    require(set(result) == set(names.split()), "Missing/unknown fields")
    return result


def integer(f, key):
    require(re.fullmatch(r"0|[1-9][0-9]*", f[key]) is not None, "Invalid unsigned integer")
    return int(f[key])


def digest(value):
    require(re.fullmatch(r"[0-9a-f]{16}", value) is not None, "Invalid digest")
    return int(value, 16)


def fold(hash_value, value):
    for byte in value.to_bytes(8, "little"):
        hash_value = ((hash_value ^ byte) * FNV_PRIME) & ((1 << 64) - 1)
    return hash_value


def check_output(text):
    require(len(BLOCKS) == 76 and len(ELIGIBLE) == 66, "Internal coverage manifest")
    require(re.search(r"FAIL|MISMATCH|Kernel panic|Illegal instruction|Assertion .*failed", text) is None,
            "Failure marker")
    results, run, case, done = [], None, None, False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        label = line.split()[0]
        if label == "M4_TU_RUN_BEGIN":
            f = fields(line, label, "run mode trace")
            index = integer(f, "run")
            require(not done and run is None and index == len(results) and index < 4, "Run ordering")
            require((integer(f, "mode"), integer(f, "trace")) == divmod(index, 2), "Run policy")
            run = dict(index=index, mode=index // 2, trace=index % 2, records=[], suite=False,
                       hash=FNV_OFFSET, rvv=0, generic=0)
        elif label == "M4_TU_CASE_BEGIN":
            require(run is not None and not run["suite"] and case is None, "Case nesting")
            f = fields(line, label, "seq dataset k frm flags vcsr")
            seq = len(run["records"])
            dataset, sub = divmod(seq, 15)
            frm, seed_index = divmod(sub, 3)
            seed = SEEDS[seed_index]
            require(dataset < 76, "Extra case")
            expected = dict(seq=seq, dataset=dataset, k=BLOCKS[dataset] * 32,
                            frm=frm, flags=seed, vcsr=(frm + seed) & 7)
            require({k: integer(f, k) for k in expected} == expected, "Case coverage/metadata")
            case = dict(**expected, traces=0)
        elif label == "GGML_RISCV_QBS_M4_PREPARE":
            require(run is not None and case is not None and run["trace"] == 1 and case["traces"] == 0,
                    "Unexpected/duplicate production trace")
            f = fields(line, label, "enabled path k")
            rvv = bool(run["mode"] and case["frm"] == 0 and case["dataset"] in ELIGIBLE)
            require(integer(f, "enabled") == run["mode"] and integer(f, "k") == case["k"] and
                    f["path"] == ("rvv" if rvv else "generic"), "Wrong production path")
            case["traces"] += 1
            run["rvv" if rvv else "generic"] += 1
        elif label == "M4_TU_CASE_PASS":
            require(run is not None and case is not None and case["traces"] == run["trace"], "Missing case/trace")
            f = fields(line, label, "seq digest fcsr vcsr")
            require(integer(f, "seq") == case["seq"], "PASS sequence mismatch")
            fcsr, vcsr = integer(f, "fcsr"), integer(f, "vcsr")
            require(fcsr >> 5 == case["frm"] and fcsr & case["flags"] == case["flags"] and
                    vcsr == case["vcsr"], "Invalid CSR snapshot")
            value = digest(f["digest"])
            run["hash"] = fold(run["hash"], value)
            run["records"].append((f["digest"], fcsr, vcsr))
            case = None
        elif label == "M4_TU_CSR_PASS":
            require(run is not None and case is None and not run["suite"], "Unexpected suite PASS")
            f = fields(line, label, "mode trace datasets checks digest bytes fcsr vcsr")
            require(integer(f, "mode") == run["mode"] and integer(f, "trace") == run["trace"] and
                    integer(f, "datasets") == 76 and integer(f, "checks") == len(run["records"]) == 1140 and
                    digest(f["digest"]) == run["hash"] and
                    all(f[k] == "exact" for k in ("bytes", "fcsr", "vcsr")), "Incomplete suite/result")
            run["suite"] = True
        elif label == "M4_TU_RUN_END":
            require(run is not None and case is None and run["suite"], "Premature run END")
            f = fields(line, label, "run exit")
            require(integer(f, "run") == run["index"] and integer(f, "exit") == 0, "Failed run")
            if results:
                require(run["records"] == results[0]["records"], "OFF/ON or trace OFF/ON differs")
            results.append(run)
            run = None
        elif label == "M4_TU_GUEST_EXIT=0":
            require(line == label and not done and run is None and len(results) == 4, "Incomplete/duplicate guest exit")
            done = True
        elif "M4_TU_" in line or "GGML_RISCV_QBS_" in line:
            raise ValueError("Unknown/malformed protocol record")
    require(done and run is None and case is None, "Truncated evidence")
    return dict(state="PASS", datasets=76, checks=4560, production_rvv_traces=results[3]["rvv"],
                production_generic_traces=results[1]["generic"] + results[3]["generic"],
                digest=f"{results[0]['hash']:016x}",
                scope="Direct production repack specialization bytes/FCSR/VCSR; not RTL performance")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: check.py SERIAL_LOG")
    print(json.dumps(check_output(Path(sys.argv[1]).read_text()), indent=2))
