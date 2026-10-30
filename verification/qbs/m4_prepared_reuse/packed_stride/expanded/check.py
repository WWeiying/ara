"""Exact acceptance, including independent call/command accounting per process."""
from collections import Counter
import math
import struct


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def matrix():
    cases = []
    for typ in ("Q4_K", "Q6_K", "Q4_0", "Q8_0"):
        for m in (1, 3, 4, 7):
            for element, pad, threads in ((4, 1, 1 + (m in (3, 7))),
                                          (8, 3, 1 + (m in (1, 4)))):
                cases.append(dict(type=typ, k=512, n=8, m=m, element=element, pad=pad, wide=0, threads=threads))
        for m in (8, 15):
            for wide in (0, 1):
                for element, pad, threads in ((4, 16, 1 + (m == 15)), (8, 1, 1 + (m == 8))):
                    cases.append(dict(type=typ, k=512, n=8, m=m, element=element, pad=pad, wide=wide, threads=threads))
        if typ == "Q6_K":
            cases.append(dict(type=typ, k=1536, n=8, m=15, element=8, pad=16, wide=1, threads=2))
    return [dict(id=i, **c) for i, c in enumerate(cases)]


def fields(line):
    return dict(word.split("=", 1) for word in line.split()[1:])


def expected_calls(c):
    m, t = c["m"], c["threads"]
    rows = [m] if c["wide"] else ([m - m % 4] if m >= 4 else []) + ([m % 4] if m % 4 else [])
    return Counter(("gemv" if r == 1 else "gemm", c["k"], r, c["n"] // t, 0)
                   for r in rows for _ in range(t))


def check_case(lines, c):
    def records(prefix):
        return [fields(l) for l in lines if l.startswith(prefix + " ")]

    require(not any(l.startswith(("XS_ERROR", "XS_FIRST_MISMATCH", "GGML_RISCV_QBS_M4_CACHE")) for l in lines),
            "error, mismatch, or unexpected cache")
    starts = records("XS_BEGIN")
    require(len(starts) == 1, "case begin")
    f = starts[0]
    require(all(f[k] == str(v) for k, v in c.items()), "case dimensions/flags")
    require(all(f[k] == v for k, v in dict(cache="0", prepare="1", context="0", emulate="0", segment="0",
                                         capture_row_k="1536").items()), "fixed configuration")
    for l in lines:
        if l.startswith("XS_"):
            require(fields(l).get("id") == str(c["id"]), "case scope")
    block, block_bytes = (256, 292) if c["type"].endswith("_K") else (32, 34)
    row_bytes = c["k"] // block * block_bytes
    plans = records("XS_PLAN")
    packed = ((c["m"] + 7) // 8 * 8 if c["wide"] else c["m"]) * row_bytes
    workspace = ((packed + 63) // 64 * 64 + c["m"] * row_bytes) if c["wide"] else packed
    require(plans == [dict(id=str(c["id"]), wide=str(c["wide"]), row_major_bytes=str(c["m"] * row_bytes),
                           packed_bytes=str(packed), workspace_bytes=str(workspace))], "actual wide planner selection/layout")
    obs = records("XS_OBSERVE")
    require([(f["side"], f["phase"]) for f in obs] == [(str(s), p) for s in (0, 1) for p in ("before", "after")],
            "complete callback order")
    side = None
    calls = {0: [], 1: []}
    prepares = {0: [], 1: []}
    for l in lines:
        if l.startswith("XS_OBSERVE "):
            f = fields(l)
            s = int(f["side"])
            element, pad = (c["element"], c["pad"]) if s else (4, 0)
            require(f["nb0"] == str(element) and f["nb1"] == str(c["k"] * element + pad * 4), "actual stride")
            require(f["same_tensor"] == f["same_data"] == f["same_backing"] == "1", "hidden contiguization")
            require(f["contiguous"] == str(int(element == 4 and (c["m"] == 1 or pad == 0))), "contiguity")
            require(f["op"] == ("PERMUTE" if element == 8 else "VIEW"), "legal view path")
            require(side is None if f["phase"] == "before" else side == s, "callback nesting")
            side = s if f["phase"] == "before" else None
        elif l.startswith("GGML_RISCV_QBS_CALL "):
            require(side is not None, "unscoped call")
            f = fields(l)
            require(f["type"].upper() == c["type"], "call format")
            calls[side].append((f["mode"], *(int(f[k]) for k in ("k", "input_rows", "output_rows", "split_k"))))
        elif l.startswith("GGML_RISCV_QBS_Q8K_M4_PREPARE "):
            require(side is not None, "unscoped producer")
            prepares[side].append(fields(l))
        elif l.startswith("GGML_RISCV_QBS_M4_PREPARE "):
            raise ValueError("Unexpected non-Zvfh Q8_0 preparation")
    for s in (0, 1):
        require(Counter(calls[s]) == expected_calls(c), f"complete calls side={s}: {calls[s]}")
        count = c["m"] // 4 if block == 256 and not c["wide"] else 0
        if s:
            count *= c["k"] // block
        expected = dict(enabled="1", path="rvv", k=str(block if s else c["k"]))
        require(len(prepares[s]) == count and all(f == expected for f in prepares[s]), f"producer blocks side={s}")
    values = records("XS_VALUE")
    require(len(values) == c["m"] * c["n"], "complete outputs")
    for i, f in enumerate(values):
        require((int(f["index"]), int(f["row"]), int(f["col"])) == (i, i // c["n"], i % c["n"]), "output order")
        for key in ("ref", "got"):
            value = struct.unpack("!f", bytes.fromhex(f[key + "_bits"]))[0]
            require(math.isfinite(value) and math.isfinite(float(f[key])), "nonfinite output")
            require(struct.pack("!f", float(f[key])).hex() == f[key + "_bits"], "decimal/bit disagreement")
        require(f["ref_bits"] == f["got_bits"], f"bit mismatch id={c['id']} index={i}: {f}")
    ends = records("XS_CASE")
    require(len(ends) == 1, "case completion")
    f = ends[0]
    require(f["outputs"] == str(len(values)) and f["mismatches"] == f["graph_status"] == "0" and f["result"] == "PASS",
            "case acceptance")
    require(all(f[k] == "1" for k in ("complete", "finite", "paired_inputs", "backing_integrity", "weight_integrity", "capture_integrity")),
            "input/weight/output integrity")
    execs = records("GGML_RISCV_QBS_EXEC")
    require(len(execs) == 1 and execs[0]["type"] == c["type"], "one native summary per fresh process")
    f = execs[0]
    all_calls = calls[0] + calls[1]
    command_m = 8 if c["wide"] else 4
    hist = Counter()
    for _, _, rows, _, _ in all_calls:
        while rows:
            step = min(rows, command_m)
            hist[step] += 1
            rows -= step
    expected = dict(gemv_calls=sum(x[0] == "gemv" for x in all_calls), gemm_calls=sum(x[0] == "gemm" for x in all_calls),
                    input_rows=sum(x[2] for x in all_calls), output_rows=sum(x[3] for x in all_calls),
                    activation_elements=sum(x[1] * x[2] for x in all_calls), output_elements=2*c["n"]*c["m"],
                    dot_elements=2*c["n"]*c["m"]*c["k"], command_dot_elements=2*c["n"]*c["m"]*c["k"],
                    native_qbexec=sum(hist.values()), emulated_commands=0, split_calls=0, segmented_commands=0,
                    context_fill=0, context_reuse=0, context_release=0)
    expected.update({f"commands_m{i}": hist[i] for i in range(1, 9)})
    require(all(int(f[k]) == v for k, v in expected.items()), f"native command accounting: expected={expected} got={f}")
    return dict(**c, outputs=len(values), native=expected, callbacks=obs, producer_calls=[len(prepares[s]) for s in (0, 1)],
                branch="wide_row_gather" if c["wide"] and c["element"] == 8 else
                       "wide_row_direct" if c["wide"] else "four_row_and_tail" if c["m"] >= 4 else "tail_only",
                exact=True, finite=True, full_integrity=True)


def check(log, cases):
    lines = log.splitlines()
    active, body, result = None, [], []
    for line in lines:
        if line.startswith("XS_PROCESS_BEGIN "):
            require(active is None and len(result) < len(cases), "nested/extra process")
            active = cases[len(result)]
            require(fields(line) == {"id": str(active["id"])}, "process order")
            body = []
        elif line.startswith("XS_PROCESS_END "):
            require(active is not None, "unscoped process exit")
            require(fields(line) == dict(id=str(active["id"]), rc="0"), "guest child failure")
            result.append(check_case(body, active))
            active = None
        elif active is not None:
            body.append(line)
        elif line.startswith(("XS_BEGIN", "XS_CASE", "XS_VALUE", "XS_OBSERVE", "XS_ERROR", "GGML_RISCV_QBS_EXEC")):
            raise ValueError("Unscoped evidence: " + line)
    require(active is None and len(result) == len(cases), "incomplete shard")
    terminal = f"XS_SHARD_PASS cases={len(cases)} matmuls={2*len(cases)} pairs={sum(c['m']*c['n'] for c in cases)} performance=not_measured"
    require([l for l in lines if l.startswith("XS_SHARD_")] == [terminal], "shard completion")
    require([l for l in lines if l.startswith("GUEST_TEST_EXIT=")] == ["GUEST_TEST_EXIT=0"], "guest exit")
    return result
