#!/usr/bin/env python3
"""Fail-closed checker for the six native GGML tile-context guest runs.

The manifest and dispatch policy are pinned to ggml_tile_context/test.cpp and
the current signoff runtime. This checks functional evidence, not performance.
The guest checks every output against its scalar oracle; trace work alone does
not prove destination addresses or numerical correctness.
"""

from collections import Counter
from dataclasses import dataclass
import math
import re


@dataclass(frozen=True)
class Shape:
    kind: str
    m: int
    blocks: int
    n: int = 37

    @property
    def elements(self):
        return 32 if self.kind == "q8_0" else 256

    @property
    def activation_bytes(self):
        return 34 if self.kind == "q8_0" else 292

    @property
    def weight_bytes(self):
        return 34 if self.kind == "q8_0" else 144

    @property
    def profiles(self):
        return (6, 2) if self.kind == "q8_0" else (1, 1)


# Explicit coverage contract: never infer the expected cases from the log.
SHAPES = (
    Shape("q8_0", 1, 1), Shape("q8_0", 3, 17),
    Shape("q8_0", 4, 28), Shape("q8_0", 4, 32), Shape("q8_0", 4, 33),
    Shape("q8_0", 5, 1), Shape("q8_0", 5, 17), Shape("q8_0", 5, 28),
    Shape("q8_0", 8, 17), Shape("q8_0", 8, 28), Shape("q8_0", 9, 17),
    Shape("q4_K", 4, 2), Shape("q4_K", 4, 4), Shape("q4_K", 4, 5),
    Shape("q4_K", 8, 2), Shape("q4_K", 8, 3),
)
RUNS = ((0, 0, 1), (1, 0, 1), (0, 1, 1),
        (1, 1, 1), (0, 1, 3), (1, 1, 3))
# EXEC uses trace_type_name(); CALL/COMMAND use ggml_type_name().
EXEC_TYPES = {"Q4_K": "q4_K", "Q8_0": "q8_0"}
COMMAND_FIELDS = (
    "seq graph_epoch activation_seq linked weight_type weight_profile "
    "activation_profile m n k_blocks access context_id context_generation "
    "segmented emulated"
).split()
CALL_FIELDS = "type mode k input_rows output_rows split_k".split()
LIFETIME_FIELDS = (
    "seq graph_epoch weight_type weight_profile activation_profile m n k "
    "bytes digest quantize_time_valid quantize_time_us"
).split()
FAILURE = re.compile(
    r"\b(?:FAIL(?:ED|URE)?|MISMATCH|UVM_ERROR|UVM_FATAL|panic)\b"
    r"|\b(?:Fatal|Error):|Assertion .* failed|Segmentation fault|Illegal instruction",
    re.I,
)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _fields(line, required, *, extra=False):
    result = {}
    for item in line.split()[1:]:
        key, separator, value = item.partition("=")
        _require(separator and key and value and key not in result,
                 "Malformed or duplicate field: " + line)
        result[key] = value
    _require(set(required) <= result.keys() if extra else set(required) == result.keys(),
             "Missing or unexpected fields: " + line)
    return result


def _int(fields, name):
    value = fields[name]
    _require(re.fullmatch(r"0|[1-9][0-9]*", value) is not None,
             "Invalid unsigned integer " + name + "=" + value)
    return int(value)


def _digest(value):
    _require(re.fullmatch(r"[0-9a-fA-F]{16}", value) is not None, "Invalid digest")
    return value.lower()


def _tiles(m, wide):
    result = []
    while m:
        rows = min(m, 8 if wide and m >= 5 else 4)
        layout = 3 if wide and rows >= 5 else 2 if not wide and rows == 4 else 1
        result.append((rows, layout))
        m -= rows
    return result


def _wide_selected(shape, enabled):
    if not enabled or shape.m < 5:
        return False

    def direct_bytes(wide):
        total = 0
        for m, _ in _tiles(shape.m, wide):
            n_limit = 16 if m >= 5 else 32
            n_tiles = (shape.n + n_limit - 1) // n_limit
            stored_m = 8 if m >= 5 else m
            total += ((shape.n + 3) // 4 * 4 * shape.weight_bytes +
                      stored_m * n_tiles * shape.activation_bytes) * shape.blocks
        return total

    narrow, wide = direct_bytes(False), direct_bytes(True)
    # Current policy estimates DIRECT traffic, not context-aware traffic.
    return narrow - wide >= (narrow * 15 + 99) // 100


def expected_dispatch(shape, context, wide, threads):
    """Return expected calls and commands; tuples retain input-tile order.

    The guest uses segmented-R4 views with segment=256, without split-K.
    N37 with three threads produces nine N4 chunks and an N1 chunk in the
    current non-NUMA GGML scheduler. Such singleton-output plans use DIRECT.
    """
    _require(threads in (1, 3), "Unsupported thread count")
    selected = _wide_selected(shape, wide)
    tiles = _tiles(shape.m, selected)
    widths = [37] if threads == 1 else [4] * 9 + [1]
    calls, commands = [], []
    for width in widths:
        calls.append((shape.kind, "gemv" if shape.m == 1 else "gemm",
                      shape.blocks * shape.elements, shape.m, width, 0))
        eligible = bool(context and shape.blocks <= 32)
        for m, layout in tiles:
            storage_rows = 8 if layout == 3 else m
            eligible &= ((layout != 1 or m == 1) and
                         storage_rows * shape.blocks * shape.activation_bytes <= 4672 and
                         width > (16 if m >= 5 else 32))
        for m, _ in tiles:
            limit = 16 if m >= 5 else 32
            ns = [min(limit, width - start) for start in range(0, width, limit)]
            for index, n in enumerate(ns):
                access = (1 if index == 0 else 3 if index == len(ns) - 1 else 2) if eligible else 0
                commands.append((m, n, shape.blocks, access))
    return calls, commands, selected


def _check_graph(graph, run):
    shape = SHAPES[graph["case"]]
    context, wide, threads = RUNS[run["index"]]
    expected_calls, expected_commands, selected = expected_dispatch(shape, context, wide, threads)
    _require(Counter(graph["calls"]) == Counter(expected_calls), "CALL partition/work differs")
    _require(sum(c[3] * c[4] for c in graph["calls"]) == shape.m * shape.n,
             "CALL output work differs")
    commands = sorted(graph["commands"], key=lambda c: c["seq"])
    end_sequence = len(run["command_sequences"])
    _require([c["seq"] for c in commands] ==
             list(range(end_sequence - len(commands) + 1, end_sequence + 1)),
             "Command sequences crossed graph boundaries or were lost/duplicated")
    signatures = [(c["m"], c["n"], c["k_blocks"], c["access"]) for c in commands]
    if threads == 1:
        _require(commands == graph["commands"], "Reordered single-thread commands")
        _require(signatures == expected_commands, "Command order/tiling/lifecycle differs")
    else:
        _require(Counter(signatures) == Counter(expected_commands), "Parallel command tiling/work differs")
    _require(sum(c["m"] * c["n"] for c in commands) == shape.m * shape.n,
             "Command output work differs")
    work = sum(c["m"] * c["n"] * c["k_blocks"] * shape.elements for c in commands)
    _require(work == shape.m * shape.n * shape.blocks * shape.elements, "Command dot work differs")
    _require(len(graph["lifetimes"]) == 1, "Missing or duplicate activation lifetime")
    lifetime = graph["lifetimes"][0]
    _require(lifetime["graph_epoch"] > 0 and lifetime["graph_epoch"] not in run["epochs"],
             "Stale or invalid graph epoch")
    _require(lifetime["seq"] == len(run["graphs"]) + 1, "Activation sequence differs")
    run["epochs"].add(lifetime["graph_epoch"])
    stored_rows = sum(8 if layout == 3 else m for m, layout in _tiles(shape.m, selected))
    _require(lifetime["bytes"] == stored_rows * shape.blocks * shape.activation_bytes,
             "Activation byte count/layout differs")
    _require(lifetime["quantize_time_valid"] == int(threads == 1), "Quantization timing scope differs")
    if threads == 3:
        _require(lifetime["quantize_time_us"] == 0, "Unexpected parallel quantization timing")

    eligible = any(c[3] for c in expected_commands)
    live = None
    for c in commands:
        _require(c["weight_type"] == shape.kind and
                 (c["weight_profile"], c["activation_profile"]) == shape.profiles and
                 c["emulated"] == 0 and c["segmented"] == 0,
                 "Non-native command or profile/segmentation mismatch")
        _require(c["linked"] in (0, 1), "Invalid activation linkage")
        if c["linked"]:
            _require((c["graph_epoch"], c["activation_seq"]) ==
                     (lifetime["graph_epoch"], lifetime["seq"]), "Stale command activation metadata")
        else:
            _require(threads == 3 and c["graph_epoch"] == 0 and c["activation_seq"] == 0,
                     "Unlinked single-thread command or inconsistent metadata")
        _require(c["context_id"] == 0 and c["context_generation"] < 256, "Invalid context token")
        if c["access"] == 0:
            _require(live is None and c["context_generation"] == 0, "DIRECT changed live context/token")
            continue
        _require(c["context_generation"] == run["generation"], "Unexpected context generation")
        metadata = (c["context_id"], c["context_generation"], c["m"],
                    c["k_blocks"], c["weight_profile"], c["activation_profile"],
                    c["graph_epoch"], c["activation_seq"])
        if c["access"] == 1:
            _require(live is None, "FILL before prior RELEASE")
            live = metadata
        else:
            _require(live == metadata, "REUSE/RELEASE without matching FILL metadata")
            if c["access"] == 3:
                live = None
    _require(live is None, "Unreleased context")
    _require(any(c["linked"] for c in commands), "No linked native command")
    if eligible:
        run["generation"] = (run["generation"] + 1) % 256
    graph.update(wide_selected=selected, context_eligible=eligible, command_dot_elements=work,
                 activation_digest=lifetime["digest"])


def _check_summaries(run):
    expected = {}
    for graph in run["graphs"]:
        kind = SHAPES[graph["case"]].kind
        counts = expected.setdefault(kind, Counter())
        for _, mode, k, m, n, split in graph["calls"]:
            counts[mode + "_calls"] += 1
            counts["input_rows"] += m
            counts["output_rows"] += n
            counts["activation_elements"] += m * k
            counts["output_elements"] += m * n
            counts["dot_elements"] += m * n * k
            counts["split_calls"] += split
        for c in graph["commands"]:
            counts["commands_m" + str(c["m"])] += 1
            counts["native_qbexec"] += 1
            counts["command_dot_elements"] += c["m"] * c["n"] * c["k_blocks"] * SHAPES[graph["case"]].elements
            if c["access"]:
                counts[{1: "context_fill", 2: "context_reuse", 3: "context_release"}[c["access"]]] += 1
    fields = ("gemv_calls gemm_calls input_rows output_rows activation_elements output_elements "
              "dot_elements split_calls native_qbexec emulated_commands command_dot_elements "
              "segmented_commands context_fill context_reuse context_release").split()
    fields += ["commands_m" + str(m) for m in range(1, 9)]
    _require(len(run["summaries"]) == len(expected), "Missing or duplicate EXEC summary")
    seen = set()
    for summary in run["summaries"]:
        kind = EXEC_TYPES.get(summary["type"])
        _require(kind in expected and kind not in seen, "Unexpected or duplicate EXEC type")
        seen.add(kind)
        _require(set(summary) == {"type", *fields}, "EXEC summary fields differ")
        for field in fields:
            _require(_int(summary, field) == expected[kind][field], "EXEC summary mismatch: " + field)
    _require(len(run["lifetime_summaries"]) == 1, "Missing unique lifetime summary")
    summary = run["lifetime_summaries"][0]
    lifetimes = [g["lifetimes"][0] for g in run["graphs"]]
    totals = dict(quantizations=len(lifetimes), graph_epochs=len(lifetimes),
                  quantized_bytes=sum(t["bytes"] for t in lifetimes),
                  quantizations_with_time=sum(t["quantize_time_valid"] for t in lifetimes),
                  quantize_time_us=sum(t["quantize_time_us"] for t in lifetimes),
                  cross_op_fill=0, cross_op_reuse=0, cross_op_release=0,
                  cross_op_quantization_skips=0, cross_op_activation_bytes_saved=0)
    for field, value in totals.items():
        _require(field in summary and _int(summary, field) == value, "Lifetime summary mismatch: " + field)


def check_output(text):
    """Validate the complete serial log or raise ValueError; return JSON data."""
    _require(isinstance(text, str), "Expected text log")
    _require(FAILURE.search(text) is None, "Failure marker in guest output")
    runs, run, graph = [], None, None
    guest_exit = False
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        label = line.split()[0]
        if label == "QBS_TILE_RUN_BEGIN":
            f = _fields(line, "run context wide threads".split())
            index = _int(f, "run")
            _require(not guest_exit and run is None and index == len(runs) and index < len(RUNS),
                     "Missing/duplicate/reordered run BEGIN")
            _require(tuple(_int(f, k) for k in ("context", "wide", "threads")) == RUNS[index],
                     "Run configuration differs")
            run = dict(index=index, graphs=[], summaries=[], lifetime_summaries=[],
                       epochs=set(), generation=0, suite=False, command_sequences=[])
        elif label == "QBS_TILE_GRAPH_BEGIN":
            _require(run is not None and not run["suite"] and graph is None, "Unnested graph BEGIN")
            f = _fields(line, "case type m n k_blocks threads epoch".split())
            case, epoch = _int(f, "case"), _int(f, "epoch")
            ordinal = len(run["graphs"])
            _require(case < len(SHAPES) and (case, epoch) == divmod(ordinal, 2), "Graph coverage/order differs")
            shape = SHAPES[case]
            _require((f["type"], _int(f, "m"), _int(f, "n"), _int(f, "k_blocks"), _int(f, "threads")) ==
                     (shape.kind, shape.m, shape.n, shape.blocks, RUNS[run["index"]][2]), "Graph shape differs")
            graph = dict(case=case, epoch=epoch, calls=[], commands=[], lifetimes=[])
        elif label == "GGML_RISCV_QBS_CALL":
            _require(graph is not None, "CALL outside graph")
            f = _fields(line, CALL_FIELDS)
            graph["calls"].append((f["type"], f["mode"], *(_int(f, k) for k in CALL_FIELDS[2:])))
        elif label == "GGML_RISCV_QBS_COMMAND":
            _require(graph is not None, "COMMAND outside graph")
            f = _fields(line, COMMAND_FIELDS)
            c = {k: f[k] if k == "weight_type" else _int(f, k) for k in COMMAND_FIELDS}
            graph["commands"].append(c)
            run["command_sequences"].append(c["seq"])
        elif label == "GGML_RISCV_QBS_LIFETIME":
            _require(graph is not None, "LIFETIME outside graph")
            f = _fields(line, LIFETIME_FIELDS, extra=True)
            t = {k: f[k] if k in ("weight_type", "digest") else _int(f, k) for k in LIFETIME_FIELDS}
            t["digest"] = _digest(t["digest"])
            shape = SHAPES[graph["case"]]
            _require((t["weight_type"], t["weight_profile"], t["activation_profile"], t["m"], t["n"], t["k"]) ==
                     (shape.kind, *shape.profiles, shape.m, shape.n, shape.blocks * shape.elements),
                     "Activation lifetime shape/profile differs")
            graph["lifetimes"].append(t)
        elif label == "QBS_TILE_GRAPH_PASS":
            _require(graph is not None, "PASS without graph")
            f = _fields(line, "outputs digest max_error".split())
            shape = SHAPES[graph["case"]]
            _require(_int(f, "outputs") == shape.m * shape.n, "Checked output count differs")
            error = float(f["max_error"])
            _require(math.isfinite(error) and error >= 0, "Invalid numerical error")
            graph.update(digest=_digest(f["digest"]), outputs=_int(f, "outputs"), max_error=error)
            _check_graph(graph, run)
            if graph["epoch"]:
                previous = run["graphs"][-1]
                _require(graph["digest"] != previous["digest"] and
                         graph["activation_digest"] != previous["activation_digest"], "Stale epoch input/output digest")
            run["graphs"].append(graph)
            graph = None
        elif label == "QBS_TILE_GRAPH_SUITE_PASS":
            _require(run is not None and graph is None and not run["suite"], "Unexpected suite PASS")
            f = _fields(line, ["cases"])
            _require(_int(f, "cases") == len(run["graphs"]) == 2 * len(SHAPES), "Incomplete graph suite")
            run["suite"] = True
        elif label in ("GGML_RISCV_QBS_EXEC", "GGML_RISCV_QBS_LIFETIME_SUMMARY"):
            _require(run is not None and run["suite"] and graph is None, "Premature/orphan summary")
            key = "summaries" if label.endswith("_EXEC") else "lifetime_summaries"
            run[key].append(_fields(line, ["type"] if key == "summaries" else ["quantizations"], extra=True))
        elif label == "QBS_TILE_RUN_END":
            _require(run is not None and graph is None and run["suite"], "Incomplete run END")
            f = _fields(line, ["run", "exit"])
            _require(_int(f, "run") == run["index"] and _int(f, "exit") == 0, "Failed or mismatched run END")
            _require(sorted(run["command_sequences"]) == list(range(1, len(run["command_sequences"]) + 1)),
                     "Missing/duplicate native command sequence")
            _check_summaries(run)
            if run["index"] % 2:
                for off, on in zip(runs[-1]["graphs"], run["graphs"]):
                    _require(on["digest"] == off["digest"] and
                             on["activation_digest"] == off["activation_digest"], "Context on/off bit digest differs")
            runs.append(run)
            run = None
        elif line.startswith("GUEST_TEST_EXIT="):
            _require(line == "GUEST_TEST_EXIT=0" and not guest_exit and run is None and len(runs) == 6,
                     "Missing runs or failed/duplicate guest exit")
            guest_exit = True
        elif label in ("GGML_RISCV_QBS_COVERAGE", "GGML_RISCV_QBS_TENSOR"):
            _require(run is not None, "QBS coverage outside run")
            _fields(line, ["type"], extra=True)
        elif any(marker in line for marker in ("QBS_TILE_", "GGML_RISCV_QBS_", "GUEST_TEST_EXIT")):
            raise ValueError("Unknown/malformed protocol record at line " + str(number))
    _require(guest_exit and run is None and graph is None and len(runs) == 6, "Incomplete guest log")
    reports = []
    for run in runs:
        eligible = sum(g["context_eligible"] for g in run["graphs"])
        reports.append(dict(run=run["index"], context=RUNS[run["index"]][0], wide=RUNS[run["index"]][1],
                            threads=RUNS[run["index"]][2], graphs=len(run["graphs"]),
                            native_commands=len(run["command_sequences"]), context_eligible_graphs=eligible,
                            context_saw_eligible=bool(eligible), outputs=sum(g["outputs"] for g in run["graphs"]),
                            command_dot_elements=sum(g["command_dot_elements"] for g in run["graphs"]),
                            digests=[g["digest"] for g in run["graphs"]]))
    return dict(state="PASS", shapes=len(SHAPES), graphs=sum(r["graphs"] for r in reports),
                runs=reports, scope="native QEMU GGML functional dispatch; not RTL performance")
