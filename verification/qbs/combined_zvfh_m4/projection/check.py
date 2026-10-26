"""Fail-closed slice checks; performance acceptance also requires current-RTL trace/UVM."""
import argparse
import csv
import json
from pathlib import Path
import re

INFO = ("7f01f1ffff100203", "20020104000e0006", "00000e08f0006ff1", "0000000100001240")
FIELDS = ("id path admit prep execute total used context wide segment commands prep_fcsr final_fcsr "
          "prep_vcsr final_vcsr input weights packed output errors").split()
FAILURE = re.compile(r"\b(?:FAIL|FAILED|MISMATCH|panic)\b|"
                     r"Q8K_CURRENT_FAIL|Assertion .*failed|Illegal instruction|Segmentation fault|"
                     r"\b(?:Error:|Fatal:|Error-\[|Fatal-\[)", re.I)
# Same complete-line zero-summary exception as ara_verify/contract.py.
UVM_ERROR = re.compile(r"\b(?:UVM_ERROR|UVM_FATAL)\b")
UVM_ZERO = re.compile(r"(?:UVM_ERROR|UVM_FATAL)[ \t]*:[ \t]*0+")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fnv(data):
    value = 14695981039346656037
    for byte in data:
        value = ((value ^ byte) * 1099511628211) & ((1 << 64) - 1)
    return f"{value:016x}"


def check_contract(contract):
    require(contract["shape"] == [4, 1536, 1536] and contract["golden_fcsr"] == 1 and
            contract["oracle_atol"] == 2e-4 and contract["oracle_rtol"] == 2e-5 and
            contract["context_capacity"] == 4672 and contract["activation_bytes"] == 7008 and
            contract["segment"] == 256 and contract["wide"] == 0 and
            contract["weight_integrity"] == "before_after_abba_exact_vector_compare", "Acceptance contract drift")
    for name in ("input", "weights", "packed"):
        require(re.fullmatch(r"[0-9a-f]{16}", contract["digests"][name]), "Invalid contract digest")


def check_output(text, contract):
    check_contract(contract)
    require(FAILURE.search(text) is None, "Failure marker")
    for raw in text.splitlines():
        line = raw.strip()
        require(not UVM_ERROR.search(line) or UVM_ZERO.fullmatch(line), "UVM error/fatal diagnostic")
    records = [line.strip() for line in text.splitlines() if "Q8K_CURRENT" in line]
    begin = "Q8K_CURRENT_BEGIN " + " ".join(f"info{i}={word}" for i, word in enumerate(INFO))
    require(len(records) == 7 and records[0] == begin, "Missing/extra protocol or wrong capability")
    trials = []
    for index, line in enumerate(records[1:5]):
        require(line.startswith("Q8K_CURRENT_TRIAL "), "Missing trial")
        fields = {}
        for item in line.split()[1:]:
            key, sep, value = item.partition("=")
            require(sep and key not in fields and value, "Malformed/duplicate field")
            fields[key] = value
        require(set(fields) == set(FIELDS), "Missing/extra trial field")
        path = "canonical" if index in (1, 2) else "generic"
        require(fields["path"] == path, "ABBA path mismatch")
        for key in ("input", "weights", "packed", "output"):
            require(re.fullmatch(r"[0-9a-f]{16}", fields[key]), "Malformed digest")
            if key != "output":
                require(fields[key] == contract["digests"][key], "Data digest mismatch: " + key)
        row = {key: fields[key] for key in ("path", "input", "weights", "packed", "output")}
        for key in set(FIELDS) - set(row):
            require(re.fullmatch(r"0|[1-9][0-9]*", fields[key]), "Invalid integer")
            row[key] = int(fields[key])
        require(row["id"] == index and row["used"] == int(path == "canonical"), "Wrong path witness")
        require((row["context"], row["wide"], row["segment"], row["commands"], row["errors"]) ==
                (0, 0, 256, 48, 0), "Policy/work/checks differ")
        require(row["prep_fcsr"] == contract["golden_fcsr"] and row["final_fcsr"] <= 31 and
                row["prep_vcsr"] == row["final_vcsr"] == 5, "CSR contract differs")
        require(all(0 < row[key] < 2**63 for key in ("admit", "prep", "execute", "total")) and
                row["total"] == row["admit"] + row["prep"] + row["execute"], "Invalid cycle intervals")
        trials.append(row)
    require(len({(r["output"], r["final_fcsr"]) for r in trials}) == 1, "Paired output/CSR differs")
    weight_hash = contract["digests"]["weights"]
    require(records[-2] == "Q8K_CURRENT_INTEGRITY scope=before_after_abba method=exact_vector_compare bytes=1327104 "
            f"reference={weight_hash} before_equal=1 after_equal=1 errors=0", "Before/after weight integrity failed")
    require(records[-1] == "Q8K_CURRENT_RESULT errors=0 m=4 n=1536 k=1536 outputs=6144 trials=4 commands=192 "
            "planner=current_sdk context=direct checks=bytes_bsums_oracle_canaries_input", "Incomplete result")
    sums = {path: {phase: sum(r[phase] for r in trials if r["path"] == path)
                   for phase in ("admit", "prep", "execute", "total")} for path in ("generic", "canonical")}
    return dict(state="GUEST_CHECKS_PASS", trials=trials, sums=sums,
                slice_speedup=sums["generic"]["total"] / sums["canonical"]["total"],
                preparation_speedup=sums["generic"]["prep"] / sums["canonical"]["prep"],
                scope="Current production quantizer + SDK planner/executor projection slice; not full GGML/model")


def check_trace(path):
    allocations, writes, slots = set(), {}, {}
    configured = False
    with Path(path).open(newline="") as stream:
        reader = csv.DictReader(stream)
        require({"event", "insn", "arch_seq", "vl", "vd", "eew", "be", "lane", "addr", "vstart",
                 "nr_lanes", "vlen_bits"} <= set(reader.fieldnames or []),
                "Incomplete trace schema")
        for row in reader:
            if row["event"] == "config":
                require(not configured and not allocations and
                        (int(row["nr_lanes"]), int(row["vlen_bits"])) == (4, 1024), "Wrong trace configuration")
                configured = True
                continue
            if row["event"] not in ("alloc", "write"):
                continue
            insn = int(row["insn"], 16)
            if insn & 127 != 0x5b:
                continue
            if insn == 0x0005155b:  # Untimed native capability queries, not QBEXEC work.
                continue
            require(insn == 0x06b5045b, "Unexpected custom execution instruction")
            sequence = int(row["arch_seq"])
            require(configured and sequence >= 0 and int(row["vstart"]) == 0 and
                    (int(row["vl"]), int(row["vd"]), int(row["eew"])) == (128, 8, 2) and
                    (int(row["nr_lanes"]), int(row["vlen_bits"])) == (4, 1024),
                    "Malformed M4 result allocation/write")
            if row["event"] == "alloc":
                require(sequence not in allocations, "Duplicate allocation")
                allocations.add(sequence)
            else:
                require(sequence in allocations, "Write without allocation")
                mask = int(row["be"], 16)
                require(0 < mask <= 255, "Invalid byte enable")
                lane, address = int(row["lane"]), int(row["addr"])
                require(0 <= lane < 4 and 32 <= address < 48, "Wrong result register address")
                seen = slots.setdefault(sequence, set())
                for byte in range(8):
                    if mask & (1 << byte):
                        slot = (lane, address, byte)
                        require(slot not in seen, "Duplicate result byte")
                        seen.add(slot)
                writes[sequence] = writes.get(sequence, 0) + bin(mask).count("1")
    require(configured and len(allocations) == 192 and set(writes) == allocations and
            all(v == 512 for v in writes.values()),
            "Incomplete/extra QBEXEC work or result bytes")
    return dict(commands=192, result_bytes=sum(writes.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("build", "log", "trace", "uvm"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    import hashlib
    build = json.loads((args.build / "build.json").read_text())
    manifest = args.build / "manifest.json"
    sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
    require(build["state"] == "READY" and sha(manifest) == build["manifest_sha256"], "Build receipt drift")
    pins = json.loads(manifest.read_text())
    require(all(sha(path) == value for path, value in pins.items()), "Build inputs/artifacts drift")
    contract = json.loads((args.build / "contract.json").read_text())
    result = check_output(args.log.read_text(), contract)
    result["traffic"] = check_trace(args.trace)
    uvm = json.loads(args.uvm.read_text())
    require(uvm["status"] == "PASS" and not uvm.get("issues"), "UVM boundary checks failed")
    result.update(state="PASS", log_sha256=sha(args.log), trace_sha256=sha(args.trace),
                  uvm_sha256=sha(args.uvm), manifest_sha256=sha(manifest))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
