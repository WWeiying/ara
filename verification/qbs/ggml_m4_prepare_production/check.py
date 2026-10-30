"""Canonical-helper and actual GGML dispatch evidence; never a timing gate."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_ggml_tile_context as tile


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_native_output(text):
    require(tile.FAILURE.search(text) is None, "Native failure marker")
    records = [line.strip() for line in text.splitlines() if "M4_PRODUCTION_" in line]
    require(records == ["M4_PRODUCTION_NATIVE_BEGIN",
                        "M4_PRODUCTION_BYTES_PASS checks=3420 vector=594 fallback=2826 bytes=exact fcsr=exact vcsr=exact",
                        "M4_PRODUCTION_NATIVE_END exit=0", "M4_PRODUCTION_NATIVE_GUEST_EXIT=0"],
            "Incomplete/extra native-only protocol")
    require(not any(m in text for m in ("QBS_TILE_", "GGML_RISCV_QBS_", "GUEST_TEST_EXIT")),
            "Unexpected graph work in native-only boot")
    return dict(state="PASS", checks=3420, vector=594, fallback=2826)


def check_graphs(text, prepare):
    clean, graph, run, count = [], None, None, 0
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("QBS_TILE_RUN_BEGIN "):
            f = tile._fields(line, "run context wide threads".split())
            run = tile._int(f, "run")
            require(run < len(tile.RUNS), "Invalid run index")
        elif line.startswith("QBS_TILE_GRAPH_BEGIN "):
            require(graph is None and run is not None, "Invalid preparation graph nesting")
            f = tile._fields(line, "case type m n k_blocks threads epoch".split())
            case = tile._int(f, "case")
            require(case < len(tile.SHAPES), "Invalid shape index")
            shape = tile.SHAPES[case]
            selected = tile._wide_selected(shape, tile.RUNS[run][1])
            expected = shape.m // 4 if shape.kind == "q8_0" and not selected else 0
            graph = dict(expected=expected, seen=0, k=shape.blocks * shape.elements)
        elif line.startswith("GGML_RISCV_QBS_M4_PREPARE"):
            require(graph is not None, "Preparation outside graph")
            require(line.split()[0] == "GGML_RISCV_QBS_M4_PREPARE", "Malformed preparation label")
            f = tile._fields(line, "enabled path k".split())
            require(tile._int(f, "enabled") == prepare and
                    f["path"] == ("rvv" if prepare else "generic") and
                    tile._int(f, "k") == graph["k"], "Wrong preparation path or shape")
            graph["seen"] += 1
            count += 1
            continue
        elif line.startswith("QBS_TILE_GRAPH_PASS "):
            require(graph is not None and graph["seen"] == graph["expected"],
                    "Missing/extra preparation calls, or unexpected wide/tail preparation")
            graph = None
        clean.append(raw)
    require(graph is None and count > 0, "No completed preparation evidence")
    result = tile.check_output("\n".join(clean))
    result["prepare_calls"] = count
    return result


def check_output(text):
    require(tile.FAILURE.search(text) is None, "Failure marker")
    phase, graphs, reports = "boot", [], []
    native_pass = False
    for raw in text.splitlines():
        line = raw.strip()
        if line == "M4_PRODUCTION_NATIVE_BEGIN":
            require(phase == "boot", "Duplicate native BEGIN")
            phase = "native"
        elif line.startswith("M4_PRODUCTION_BYTES_PASS"):
            require(phase == "native" and not native_pass, "Unexpected byte result")
            f = tile._fields(line, "checks vector fallback bytes fcsr vcsr".split())
            require(f == dict(checks="3420", vector="594", fallback="2826",
                              bytes="exact", fcsr="exact", vcsr="exact"), "Incomplete byte/CSR matrix")
            native_pass = True
        elif line.startswith("M4_PRODUCTION_NATIVE_END"):
            require(phase == "native" and native_pass and
                    line == "M4_PRODUCTION_NATIVE_END exit=0", "Native failure or missing result")
            phase = "between"
        elif line.startswith("M4_PRODUCTION_GRAPH_BEGIN"):
            require(phase == "between" and len(reports) < 2 and
                    line == f"M4_PRODUCTION_GRAPH_BEGIN prepare={len(reports)}", "Invalid graph group BEGIN")
            phase, graphs = "graphs", []
        elif line.startswith("M4_PRODUCTION_GRAPH_END"):
            require(phase == "graphs" and
                    line == f"M4_PRODUCTION_GRAPH_END prepare={len(reports)} exit=0", "Invalid graph group END")
            reports.append(check_graphs("\n".join(graphs), len(reports)))
            phase = "between"
        elif line.startswith("M4_PRODUCTION_GUEST_EXIT"):
            require(phase == "between" and len(reports) == 2 and
                    line == "M4_PRODUCTION_GUEST_EXIT=0", "Incomplete or failed guest")
            phase = "done"
        elif "M4_PRODUCTION_" in line:
            raise ValueError("Unknown/malformed production protocol")
        elif phase == "graphs":
            graphs.append(raw)
        elif any(marker in line for marker in ("QBS_TILE_", "GGML_RISCV_QBS_", "GUEST_TEST_EXIT")):
            raise ValueError("Graph evidence outside graph group")
    require(phase == "done" and len(reports) == 2, "Truncated guest output")
    for off, on in zip(reports[0]["runs"], reports[1]["runs"]):
        require(off["digests"] == on["digests"], "Preparation OFF/ON output bits differ")
    require(reports[0]["prepare_calls"] == reports[1]["prepare_calls"], "Preparation work differs")
    return dict(state="PASS", native_checks=3420, graphs=sum(r["graphs"] for r in reports),
                prepare_calls_per_mode=reports[0]["prepare_calls"], modes=reports,
                scope="Native QEMU functional byte/CSR and GGML path gate; no performance claim")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: check.py SERIAL_LOG")
    print(json.dumps(check_output(Path(sys.argv[1]).read_text()), indent=2))
