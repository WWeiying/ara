"""Reconcile complete ordinary-RVV outputs and stop-on-first-failure evidence."""
import math
import struct

MATRIX = [(4, 4, 16), (7, 4, 16), (4, 8, 3), (7, 8, 3)]


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def fields(line):
    return dict(word.split("=", 1) for word in line.split()[1:])


def check(log):
    lines = log.splitlines()
    cases, current = [], None
    for line in lines:
        require(not line.startswith(("RF_ERROR", "GGML_RISCV_QBS_CALL ", "GGML_RISCV_QBS_EXEC ",
                                     "GGML_RISCV_REPACK=QBS ", "GGML_RISCV_QBS_M4_CACHE ",
                                     "GGML_RISCV_QBS_M4_SELECTED ")), "Unexpected failure/QBS execution: " + line)
        if line.startswith("RF_BEGIN "):
            require(current is None and len(cases) < 4 and not any(c["mismatches"] for c in cases), "Extra dispatch after failure")
            f = fields(line)
            m, element, pad = MATRIX[len(cases)]
            require(f == dict(id=str(len(cases)), type="Q4_K", k="512", n="32", m=str(m), element=str(element), pad=str(pad)), "Case geometry/order")
            current = dict(spec=f, values=[], observations=[], rows=[], first=[], weights=[], repacks=0, decisions=0, prepares=[])
        elif line.startswith("GGML_RISCV_REPACK="):
            require(current is not None and line == "GGML_RISCV_REPACK=Q4_K_32x1_Q8_K shape=512x32", "Not ordinary RVV repack")
            current["repacks"] += 1
        elif line.startswith("GGML_RISCV_QBS_TENSOR "):
            f = fields(line)
            require(current is not None and f["decision"] == "runtime_disabled" and f["type"] == "q4_K" and
                    f["k"] == "512" and f["rows"] == "32" and f["segmented"] == "0", "QBS selection")
            current["decisions"] += 1
        elif line.startswith("GGML_RISCV_QBS_Q8K_M4_PREPARE "):
            require(current is not None, "Unscoped producer")
            current["prepares"].append(fields(line))
        elif line.startswith(("RF_VALUE ", "RF_OBSERVE ", "RF_FIRST ", "RF_ROW ", "RF_WEIGHT ", "RF_CASE ")):
            f = fields(line)
            require(current is not None and f["id"] == current["spec"]["id"], "Record scope")
            kind = line.split()[0]
            if kind != "RF_CASE":
                current[{"RF_VALUE": "values", "RF_OBSERVE": "observations", "RF_FIRST": "first",
                         "RF_ROW": "rows", "RF_WEIGHT": "weights"}[kind]].append(f)
                continue
            m, element, pad = MATRIX[len(cases)]
            require(current["repacks"] >= 1 and current["decisions"] >= 1, "Missing actual fallback selection")
            require(current["prepares"] == [dict(enabled="0", path="generic", k="512")]*3, "Wrong activation producer")
            require(len(current["weights"]) == 1, "Weight ownership record")
            w = current["weights"][0]
            require(all(w[k] == v for k, v in dict(buffer="CPU_REPACK", qbs_supported="0", owned="1", captured="1").items()) and
                    w["extra"] not in ("(nil)", "0x0") and w["data"] not in ("(nil)", "0x0"), "Weight ownership")
            obs = current["observations"]
            require([(o["side"], o["phase"]) for o in obs] == [(str(s), p) for s in range(3) for p in ("before", "after")], "Complete graph callbacks")
            for o in obs:
                s = int(o["side"])
                step = element if s == 2 else 4
                require(int(o["nb0"]) == step and int(o["nb1"]) == 512*step + (pad*4 if s == 2 else 0), "Changed source strides")
                require(o["contiguous"] == str(int(s != 2)) and o["op"] == ("PERMUTE" if step == 8 else "VIEW") and
                        o["same_tensor"] == o["same_data"] == o["same_backing"] == "1", "Contiguized/replaced source")
            values = current["values"]
            require(len(values) == 32*m, "Incomplete output dump")
            mismatches = []
            row_counts = [0]*m
            for i, v in enumerate(values):
                require((int(v["index"]), int(v["row"]), int(v["col"])) == (i, i//32, i%32), "Output order")
                for name in ("ref", "control", "got"):
                    value = struct.unpack("!f", bytes.fromhex(v[name + "_bits"]))[0]
                    require(math.isfinite(value) and math.isfinite(float(v[name])) and
                            struct.pack("!f", float(v[name])).hex() == v[name + "_bits"], "Nonfinite/inconsistent output")
                require(v["ref_bits"] == v["control_bits"], "Dense-repeat control mismatch")
                if v["ref_bits"] != v["got_bits"]:
                    mismatches.append(v)
                    row_counts[i//32] += 1
            expected_first = [{k: mismatches[0][k] for k in ("id", "index", "row", "col", "ref_bits", "got_bits")}] if mismatches else []
            require(current["first"] == expected_first, "First mismatch evidence")
            require(current["rows"] == [dict(id=f["id"], row=str(r), mismatches=str(n), outputs="32") for r, n in enumerate(row_counts)], "Row mismatch counts")
            require(int(f["outputs"]) == len(values) and int(f["mismatches"]) == len(mismatches) and
                    f["control_mismatches"] == f["graph_status"] == "0", "Case accounting")
            require(all(f[k] == "1" for k in ("complete", "finite", "paired_inputs", "backing_integrity", "weight_integrity", "capture_integrity")), "Integrity/completion")
            require(f["result"] == ("FAIL" if mismatches else "PASS"), "False case status")
            cases.append(dict(id=len(cases), m=m, element=element, pad=pad, k=512, n=32,
                              outputs=len(values), mismatches=len(mismatches), row_mismatches=row_counts,
                              affected_rows=[r for r, n in enumerate(row_counts) if n],
                              equal_rows=[r for r, n in enumerate(row_counts) if not n],
                              first_mismatch=expected_first[0] if expected_first else None,
                              dense_control_pass=True, fallback_repack_traces=current["repacks"]))
            current = None
    require(current is None and cases, "Incomplete suite")
    failed = bool(cases[-1]["mismatches"])
    require(failed or len(cases) == 4, "Unexplained early stop")
    reason = "first_mismatch" if failed else "not_reproduced"
    terminal = f"RF_STOP reason={reason} planned=4 completed={len(cases)} skipped={4-len(cases)} performance=not_measured"
    require([l for l in lines if l.startswith("RF_STOP ")] == [terminal], "Stop contract")
    require([l for l in lines if l.startswith("GUEST_TEST_EXIT=")] == [f"GUEST_TEST_EXIT={int(failed)}"], "Guest exit status")
    config = "RF_CONFIG qbs=0 emulate=0 prepare=0 packed=0 cache=0 context=0 wide=0 threads=1 vlen=1024 vl32=32"
    require([l for l in lines if l.startswith("RF_CONFIG ")] == [config], "Configuration")
    coverage = [fields(l) for l in lines if l.startswith("GGML_RISCV_QBS_COVERAGE ")]
    require(coverage and all(f["selected_tensors"] == "0" and int(f["fallback_runtime"]) > 0 for f in coverage), "QBS fallback accounting")
    return dict(conclusion="CONFIRMED" if failed else "NOT_REPRODUCED", cases=cases,
                completed_cases=len(cases), skipped_cases=4-len(cases), native_qbs_calls=0,
                dense_controls_pass=True, performance_measured=False, rtl_evidence=False)
