#!/usr/bin/env python3
"""Fail-closed static gate for the pinned Cheshire single-hart PLIC contract.

--plic-dir is an ipgen output root containing data/ and rtl/, not rtl/ alone.
Requires hjson (lazy import; already listed in python-requirements.txt). An
optional root rv_plic.cfg.hjson is checked too; data/rv_plic.ipconfig.hjson is
always required. The contract is fixed from Cheshire cd73fd892a09/hw/rv_plic.cfg.hjson:
src=58 includes reserved ID 0, target=2 means M/S contexts, prio=7, nonstd_regs=0.

HJSON is structurally parsed. SV checks recognize selected pinned-generator
declarations, register offsets and connections, after removing comments/strings.
They are NOT an SV parser, preprocessor, elaborator, driver analysis or functional
proof. Unrecognized required forms fail; arbitrary unexamined logic may still be
wrong. In particular, the source-0 ASSUME does not prove the SoC ties it low.
Gateway/target default N_SOURCE=32 is intentional: the core must override it.

Optional DTS is compiled by dtc into a disposable DTB and queried with fdtget,
with a shared 15-second deadline. Only the two known initrd template placeholders
may be substituted, strictly in their initrd properties; this does not validate
the eventual boot DTB. Includes/preprocessing are not supported. No EDA is run.
Without DTS, STATIC_PASS covers the PLIC files only, not software integration.
JSON is printed on stdout. --output exclusively creates a report outside the
PLIC input tree. Exit 0 = STATIC_PASS, 1 = FAIL, 2 = report/CLI error.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib
import json
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time


CONTRACT = {"src": 58, "target": 2, "prio": 7, "nonstd_regs": 0}
PARAMS = {"NumSrc": 58, "NumTarget": 2, "PrioWidth": 3}
RTL_FILES = ("rv_plic_reg_pkg", "rv_plic_reg_top", "rv_plic",
             "rv_plic_gateway", "rv_plic_target")
MAX_INPUT_BYTES = 2 * 1024 * 1024


class CheckError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise CheckError(message)


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        require(name not in result, f"duplicate object key: {name}")
        result[name] = value
    return result


def integer(value):
    if type(value) is int:
        return value
    if isinstance(value, str) and re.fullmatch(r"(?:0[xX][0-9a-fA-F]+|[0-9]+)", value):
        return int(value, 16 if value.lower().startswith("0x") else 10)
    raise CheckError(f"expected unsigned integer literal, got {value!r}")


def true(value):
    return value is True or (isinstance(value, str) and value.lower() == "true")


def named(items):
    require(isinstance(items, list), "expected a list of named objects")
    require(all(isinstance(x, dict) and isinstance(x.get("name"), str) for x in items),
            "expected named objects")
    return unique_object((x["name"], x) for x in items)


def expected_offsets():
    offsets = {f"PRIO{i}": 4 * i for i in range(58)}
    offsets.update({"IP_0": 0x1000, "IP_1": 0x1004})
    for context in range(2):
        for word in range(2):
            offsets[f"IE{context}_{word}"] = 0x2000 + context * 0x80 + word * 4
        offsets[f"THRESHOLD{context}"] = 0x200000 + context * 0x1000
        offsets[f"CC{context}"] = 0x200004 + context * 0x1000
    offsets.update(MSIP0=0x3FFFFF8, ALERT_TEST=0x3FFFFFC)
    return offsets


def check_config(config):
    require(isinstance(config, dict), "configuration must be an object")
    require(config.get("instance_name") == "rv_plic", "instance_name must be rv_plic")
    values = config.get("param_values")
    require(isinstance(values, dict), "param_values must be an object")
    require(set(values) in (set(CONTRACT), set(CONTRACT) | {"module_instance_name"}),
            "explicit src/target/prio/nonstd_regs required; defaults/unknown parameters rejected")
    require({k: integer(values[k]) for k in CONTRACT} == CONTRACT,
            f"expected {CONTRACT}; 58 slots include reserved source 0, not 58 device IRQs")
    require(values.get("module_instance_name", "rv_plic") == "rv_plic",
            "module_instance_name must be rv_plic")


def check_hjson(description):
    require(isinstance(description, dict), "register description must be an object")
    require(description.get("name") == "rv_plic", "register block must be rv_plic")
    require(integer(description.get("regwidth")) == 32, "regwidth must be 32")
    params = named(description.get("param_list"))
    require(set(params) == set(PARAMS), "unexpected/missing HJSON parameters")
    for name, expected in PARAMS.items():
        require(integer(params[name].get("default")) == expected, f"HJSON {name} != {expected}")
        require(params[name].get("type") == "int" and true(params[name].get("local")),
                f"HJSON {name} must be a local integer")
    require(description.get("bus_interfaces") == [{"protocol": "reg_iface", "direction": "device"}],
            "expected pinned reg_iface device interface")
    require(true(description.get("no_auto_alert_regs")), "automatic alert registers alter the map")
    signals = named(description.get("inter_signal_list"))
    for signal in ("irq", "msip"):
        require(signal in signals and integer(signals[signal].get("width")) == 2,
                f"{signal} must have two contexts")

    registers = description.get("registers")
    require(isinstance(registers, list), "registers must be a list")
    logical, offsets, cursor = {}, {}, 0
    for entry in registers:
        require(isinstance(entry, dict), "register entry must be an object")
        if set(entry) == {"skipto"}:
            next_offset = integer(entry["skipto"])
            require(next_offset >= cursor and next_offset % 4 == 0, "invalid/backwards skipto")
            cursor = next_offset
            continue
        multi = "multireg" in entry
        require(not multi or set(entry) == {"multireg"}, "unsupported multireg wrapper")
        reg = entry["multireg"] if multi else entry
        require(isinstance(reg, dict) and isinstance(reg.get("name"), str), "missing register name")
        name = reg["name"]
        require(name not in logical, f"duplicate register: {name}")
        logical[name] = reg
        fields = reg.get("fields")
        require(isinstance(fields, list) and len(fields) == 1 and isinstance(fields[0], dict),
                f"{name}: expected one field in pinned register schema")
        bits = str(fields[0].get("bits"))
        if multi:
            require(name in {"IP", "IE0", "IE1"}, f"unexpected multireg {name}")
            count = reg.get("count")
            count = PARAMS[count] if isinstance(count, str) and count in PARAMS else integer(count)
            require(count == 58 and bits == "0" and true(reg.get("compact", True)),
                    f"{name}: expected 58 packed single-bit slots including source 0")
            require(not true(reg.get("regwen_multi", False)) and "regwen" not in reg,
                    f"{name}: unsupported register write gating")
            width, sw, hw = "0", "ro" if name == "IP" else "rw", "hwo" if name == "IP" else "hro"
            names = [f"{name}_0", f"{name}_1"]
        else:
            require(name in expected_offsets() and not name.startswith(("IP_", "IE")),
                    f"unexpected/non-multireg register {name}")
            width = "5:0" if name.startswith("CC") else "0" if name in {"MSIP0", "ALERT_TEST"} else "2:0"
            sw, hw = ("wo", "hro") if name == "ALERT_TEST" else ("rw", "hrw" if name.startswith("CC") else "hro")
            if name.startswith("CC"):
                require(all(true(reg.get(k)) for k in ("hwext", "hwqe", "hwre")),
                        f"{name}: claim/complete strobes missing")
            names = [name]
        require(bits == width and reg.get("swaccess") == sw and reg.get("hwaccess") == hw,
                f"{name}: incorrect field width/access contract")
        for flat in names:
            require(flat not in offsets, f"duplicate flattened register: {flat}")
            offsets[flat] = cursor
            cursor += 4
    require(offsets == expected_offsets(), "HJSON register map differs from 58/2/7/0 (including 0x80 IE stride)")
    require(cursor == 1 << 26, "register extent must produce BlockAw=26")


def sv_code(text):
    # This is a lexical filter for signature checks, not a Verilog parser.
    token = r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"'
    code = re.sub(token, " ", text, flags=re.S)
    require(not re.search(r"(?m)^\s*`(?:ifdef|ifndef|elsif|else|endif|define|undef)\b", code),
            "conditional/macro-defined SV is outside the pinned signature checker")
    return code


def module(code, name):
    matches = re.findall(r"\bmodule\s+" + re.escape(name) + r"\b.*?\bendmodule\b", code, re.S)
    require(len(matches) == 1, f"expected exactly one module {name}")
    return matches[0]


def compact(code):
    return re.sub(r"\s+", "", code)


def int_parameter(code, name, expected):
    matches = re.findall(r"\b(?:localparam|parameter)\s+int\s+(?:unsigned\s+)?" +
                         re.escape(name) + r"\s*=\s*([0-9]+)\s*(?=[,;\n)])", code)
    require(matches == [str(expected)], f"{name}: expected unique literal {expected}, found {matches}")


def signature(code, text):
    require(compact(text) in compact(code), f"missing pinned SV signature: {text}")


def assignment(code, lhs, rhs):
    assignments = [compact(x) for x in re.findall(r"\bassign\s+([^;]+);", code)]
    values = [x.split("=", 1)[1] for x in assignments if x.split("=", 1)[0] == compact(lhs)]
    require(values == [compact(rhs)], f"{lhs}: expected one assignment to {rhs}, got {values}")


def check_pkg(code):
    require(len(re.findall(r"\bpackage\s+rv_plic_reg_pkg\s*;", code)) == 1,
            "missing/duplicate rv_plic_reg_pkg")
    for name, expected in {**PARAMS, "BlockAw": 26, "NumAlerts": 1}.items():
        int_parameter(code, name, expected)
    offsets = unique_object((name, int(value.replace("_", ""), 16)) for name, value in re.findall(
        r"parameter\s+logic\s*\[BlockAw\s*-\s*1\s*:\s*0\]\s+RV_PLIC_(\w+)_OFFSET\s*=\s*26'h\s*([0-9a-fA-F_]+)\s*;", code))
    require(offsets == expected_offsets(), "package offsets differ/missing; expected 26-bit 58/2 map")
    for name in [f"prio{i}" for i in range(58)] + ["threshold0", "threshold1"]:
        typename = f"rv_plic_reg2hw_{name}_reg_t"
        signature(code, f"typedef struct packed {{ logic [2:0] q; }} {typename};")
        signature(code, f"{typename} {name};")
    for context in range(2):
        signature(code, f"rv_plic_reg2hw_ie{context}_mreg_t [57:0] ie{context};")
        for direction, field in (("reg2hw", "q"), ("hw2reg", "d")):
            name = f"rv_plic_{direction}_cc{context}_reg_t"
            matches = re.findall(r"typedef\s+struct\s+packed\s*\{([^{}]*)\}\s*" + name + r"\s*;", code)
            require(len(matches) == 1, f"missing/duplicate {name}")
            signature(matches[0], f"logic [5:0] {field};")
            if direction == "reg2hw":
                signature(matches[0], "logic qe;")
                signature(matches[0], "logic re;")
            signature(code, f"{name} cc{context};")
    signature(code, "rv_plic_hw2reg_ip_mreg_t [57:0] ip;")


def check_top(code):
    code = module(code, "rv_plic_reg_top")
    int_parameter(code, "AW", 26)
    for lhs, rhs in {
        "reg_addr": "reg_intf_req.addr[BlockAw-1:0]",
        "reg_error": "(devmode_i & addrmiss) | wr_err",
        "reg_intf_rsp.error": "reg_error",
    }.items():
        assignment(code, lhs, rhs)
    hits = re.findall(r"addr_hit\s*\[\s*(\d+)\s*\]\s*=\s*\(\s*reg_addr\s*==\s*RV_PLIC_(\w+)_OFFSET\s*\)\s*;", code)
    require(Counter(name for _, name in hits) == Counter(expected_offsets().keys()),
            "reg_top decode missing/duplicate/wrong register offsets")
    require(sorted(int(index) for index, _ in hits) == list(range(len(expected_offsets()))),
            "reg_top duplicate/missing address-hit index")
    for name in [f"prio{i}" for i in range(58)] + ["threshold0", "threshold1"]:
        require(len(re.findall(r"\.q\s*\(\s*reg2hw\." + name + r"\.q\s*\)", code)) == 1,
                f"reg_top {name}: missing/duplicate q connection")
    for context in range(2):
        signature(code, f"logic [5:0] cc{context}_qs;")
        signature(code, f"logic [5:0] cc{context}_wd;")
        indices = re.findall(r"\.q\s*\(\s*reg2hw\.ie" + str(context) + r"\s*\[\s*(\d+)\s*\]\.q\s*\)", code)
        require(sorted(map(int, indices)) == list(range(58)), f"reg_top IE{context} must connect all 58 slots")
        for port, wire in (("d", f"hw2reg.cc{context}.d"), ("qre", f"reg2hw.cc{context}.re"),
                           ("qe", f"reg2hw.cc{context}.qe"), ("q", f"reg2hw.cc{context}.q")):
            require(len(re.findall(r"\." + port + r"\s*\(\s*" + re.escape(wire) + r"\s*\)", code)) == 1,
                    f"reg_top CC{context}: missing/duplicate {port} connection")
    indices = re.findall(r"\.d\s*\(\s*hw2reg\.ip\s*\[\s*(\d+)\s*\]\.d\s*\)", code)
    require(sorted(map(int, indices)) == list(range(58)), "reg_top IP must connect all 58 slots")


def instance(code, kind, name, parameters, ports):
    matches = re.findall(re.escape(kind) + r"\s*#\s*\((.*?)\)\s*" + re.escape(name) +
                         r"\s*\((.*?)\)\s*;", code, re.S)
    require(len(matches) == 1, f"missing/duplicate {kind} {name}")
    for body, expected in zip(matches[0], (parameters, ports)):
        pairs = unique_object((key, compact(value)) for key, value in
                              re.findall(r"\.(\w+)\s*\(([^()]*)\)", body))
        for key, value in expected.items():
            require(pairs.get(key) == value, f"{name}.{key}: expected {value}, got {pairs.get(key)}")


def check_core(code):
    code = module(code, "rv_plic")
    int_parameter(code, "MAX_PRIO", 7)
    signature(code, "input [NumSrc-1:0] intr_src_i,")
    signature(code, "output [NumTarget-1:0] irq_o,")
    signature(code, "localparam int SRCW = $clog2(NumSrc)")
    assignment(code, "msip_o", "'0")
    assignment(code, "cc_id", "irq_id_o")
    for source in range(58):
        assignment(code, f"prio[{source}]", f"reg2hw.prio{source}.q")
    require(sorted(map(int, re.findall(r"\bassign\s+prio\s*\[\s*(\d+)\s*\]", code))) == list(range(58)),
            "priority source coverage must be exactly 0..57")
    for context in range(2):
        signature(code, f"for (genvar s = 0; s < 58; s++) begin : gen_ie{context} "
                        f"assign ie[{context}][s] = reg2hw.ie{context}[s].q; end")
        for lhs, rhs in {
            f"ie[{context}][s]": f"reg2hw.ie{context}[s].q",
            f"threshold[{context}]": f"reg2hw.threshold{context}.q",
            f"claim_re[{context}]": f"reg2hw.cc{context}.re",
            f"claim_id[{context}]": f"irq_id_o[{context}]",
            f"complete_we[{context}]": f"reg2hw.cc{context}.qe",
            f"complete_id[{context}]": f"reg2hw.cc{context}.q",
            f"hw2reg.cc{context}.d": f"cc_id[{context}]",
        }.items():
            assignment(code, lhs, rhs)
    require(sorted(re.findall(r"\bbegin\s*:\s*gen_ie(\d+)\b", code)) == ["0", "1"],
            "core must generate exactly IE0 and IE1")
    signature(code, "for (genvar s = 0; s < 58; s++) begin : gen_ip "
                    "assign hw2reg.ip[s].de = 1'b1; assign hw2reg.ip[s].d = ip[s]; end")
    signature(code, "for (genvar i = 0; i < NumTarget; i++) begin : gen_target")
    signature(code, "`ASSUME(Irq0Tied_A, intr_src_i[0] == 1'b0)")
    instance(code, "rv_plic_gateway", "u_gateway", {"N_SOURCE": "NumSrc"},
             {"src_i": "intr_src_synced", "le_i": "LevelEdgeTrig", "claim_i": "claim",
              "complete_i": "complete", "ip_o": "ip"})
    instance(code, "rv_plic_target", "u_target", {"N_SOURCE": "NumSrc", "MAX_PRIO": "MAX_PRIO"},
             {"ip_i": "ip", "ie_i": "ie[i]", "prio_i": "prio", "threshold_i": "threshold[i]",
              "irq_o": "irq_o[i]", "irq_id_o": "irq_id_o[i]"})
    instance(code, "rv_plic_reg_top", "u_reg", {"reg_req_t": "reg_req_t", "reg_rsp_t": "reg_rsp_t"},
             {"devmode_i": "1'b1"})


def check_helper(code, name):
    code = module(code, name)
    # Both pinned templates retain this default; the checked core overrides it.
    int_parameter(code, "N_SOURCE", 32)
    if name == "rv_plic_target":
        int_parameter(code, "MAX_PRIO", 7)
        signature(code, "localparam int SrcWidth = $clog2(N_SOURCE),")
        signature(code, ".NumSrc(N_SOURCE)")
    else:
        signature(code, "input [N_SOURCE-1:0] src_i,")
        signature(code, "output logic [N_SOURCE-1:0] ip_o")


def check_dts(path, text):
    require(not re.search(r'/include/|/incbin/|(?m:^\s*#\s*(?:include|define))', text),
            "DTS must be self-contained; includes/preprocessing are not audited")
    substitutions = {}
    for suffix, placeholder, value in (("start", "__INITRD_START__", "0x88000000"),
                                        ("end", "__INITRD_END__", "0x88001000")):
        if placeholder in text:
            pattern = (r"(linux,initrd-" + suffix + r"\s*=\s*<\s*(?:0x0|0)\s+)" +
                       placeholder + r"(\s*>\s*;)")
            require(text.count(placeholder) == 1 and len(re.findall(pattern, text)) == 1,
                    f"{placeholder} is supported only in its initrd property")
            text = re.sub(pattern, lambda m: m[1] + value + m[2], text)
            substitutions[placeholder] = value
    require(not re.search(r"__[A-Z][A-Z0-9_]*__", text), "unknown/unresolved DTS template placeholder")
    tools = {name: shutil.which(name) for name in ("dtc", "fdtget")}
    require(all(tools.values()), "configuration error: dtc and fdtget are required for --dts")
    deadline = time.monotonic() + 15

    def run(argv):
        remaining = deadline - time.monotonic()
        require(remaining > 0, "DTS inspection exceeded 15-second deadline")
        result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=min(5, remaining), check=False)
        require(result.returncode == 0, f"DT tool failed: {result.stderr.decode(errors='replace')[:1000]}")
        require(len(result.stdout) <= MAX_INPUT_BYTES, "DT tool output too large")
        return result.stdout

    with tempfile.TemporaryDirectory(prefix="plic-dt-") as temporary:
        dtb = str(Path(temporary) / "input.dtb")
        # Compile the exact already-hashed bytes, never re-open a drifting DTS.
        source = Path(temporary) / "input.dts"
        source.write_text(text, encoding="utf-8")
        run([tools["dtc"], "-I", "dts", "-O", "dtb", "-o", dtb, str(source)])

        def get(node, prop, kind="x"):
            value = run([tools["fdtget"], "-t", kind, dtb, node, prop]).decode().split()
            return value if kind == "s" else [int(v, 16) for v in value]

        nodes, queue = {}, ["/"]
        cell_props = {"#address-cells", "#size-cells", "#interrupt-cells", "phandle", "reg", "ranges",
                      "riscv,ndev", "riscv,max-priority", "interrupts-extended"}
        while queue:
            require(len(nodes) + len(queue) <= 128, "DTS exceeds 128-node inspection limit")
            node = queue.pop()
            properties = run([tools["fdtget"], "-p", dtb, node]).decode().split()
            record = {name: True for name in properties}
            for prop in set(properties) & cell_props:
                record[prop] = get(node, prop)
            for prop in set(properties) & {"compatible", "status", "device_type"}:
                record[prop] = get(node, prop, "s")
            nodes[node] = record
            children = run([tools["fdtget"], "-l", dtb, node]).decode().split()
            queue.extend(node.rstrip("/") + "/" + name for name in children)

    candidates = [(node, data) for node, data in nodes.items()
                  if set(data.get("compatible", [])) & {"riscv,plic0", "sifive,plic-1.0.0"}]
    require(len(candidates) == 1, "DTS must contain exactly one supported PLIC")
    node, plic = candidates[0]
    for prop, expected in {"riscv,ndev": [57], "riscv,max-priority": [7],
                           "#interrupt-cells": [1], "#address-cells": [0],
                           "reg": [0, 0x04000000, 0, 0x04000000]}.items():
        require(plic.get(prop) == expected, f"DTS {prop}: expected {expected}, got {plic.get(prop)}")
    require(plic.get("interrupt-controller") is True, "PLIC must be an interrupt-controller")
    require(plic.get("status", ["okay"]) in (["okay"], ["ok"]), "PLIC is disabled")
    parent = nodes[node.rsplit("/", 1)[0] or "/"]
    require(parent.get("#address-cells") == [2] and parent.get("#size-cells") == [2],
            "PLIC parent must explicitly use two address and size cells")
    ancestor = node.rsplit("/", 1)[0] or "/"
    while ancestor != "/":
        bus = nodes[ancestor]
        require(bus.get("ranges") == [], "PLIC ancestor ranges must explicitly be identity (empty)")
        require(bus.get("status", ["okay"]) in (["okay"], ["ok"]), "PLIC ancestor bus is disabled")
        require(bus.get("#address-cells") == [2] and bus.get("#size-cells") == [2],
                "PLIC ancestor bus must use two address and size cells")
        ancestor = ancestor.rsplit("/", 1)[0] or "/"
    require(nodes["/"].get("#address-cells") == [2] and nodes["/"].get("#size-cells") == [2],
            "DTS root must use two address and size cells")
    contexts = plic.get("interrupts-extended", [])
    require(len(contexts) == 4 and contexts[0] == contexts[2] and contexts[1::2] == [11, 9],
            "DTS contexts must be same-hart M(11) then S(9), not two harts or swapped contexts")
    controllers = [(name, data) for name, data in nodes.items() if data.get("phandle") == [contexts[0]]]
    require(len(controllers) == 1, "CPU interrupt-controller phandle must resolve uniquely")
    intc_node, intc = controllers[0]
    require("riscv,cpu-intc" in intc.get("compatible", []) and intc.get("#interrupt-cells") == [1]
            and intc.get("interrupt-controller") is True, "context phandle must refer to a RISC-V CPU intc")
    require(intc.get("status", ["okay"]) in (["okay"], ["ok"]), "CPU interrupt-controller is disabled")
    cpu = nodes.get(intc_node.rsplit("/", 1)[0], {})
    require(cpu.get("device_type") == ["cpu"] and cpu.get("reg") == [0]
            and cpu.get("status", ["okay"]) in (["okay"], ["ok"]), "contexts must belong to enabled hart0")
    return {"status": "STATIC_PASS", "node": node, "source_count": 57,
            "contexts": ["hart0:M", "hart0:S"], "tools": tools,
            "input_kind": "DTS_TEMPLATE" if substitutions else "DTS",
            "template_substitutions": substitutions, "boot_dtb": "NOT_VALIDATED"}


def check_plic(plic_dir: Path, dts_path: Path | None = None) -> dict:
    root = Path(plic_dir).resolve()
    result = {"schema_version": 1, "plic_dir": str(root), "status": "FAIL", "accepted": False,
              "contract": {**CONTRACT, "BlockAw": 26, "PrioWidth": 3, "ndev": 57,
                           "source_zero": "reserved; src includes zero; SoC tie-off NOT_VALIDATED"},
              "scope": "pinned generated-file static signatures; NOT an SV parser or functional proof",
              "functional_status": "NOT_VALIDATED", "soc_wiring": "NOT_VALIDATED",
              "os_custom_context": "NOT_VALIDATED", "elaboration": "NOT_RUN",
              "dts": {"status": "NOT_CHECKED"}, "files": {}, "checks": [], "errors": []}

    def attempt(label, action):
        try:
            value = action()
        except (CheckError, OSError, UnicodeError, ValueError, TypeError, KeyError,
                ImportError, subprocess.SubprocessError) as error:
            result["errors"].append({"check": label, "message": str(error)})
            result["checks"].append({"check": label, "status": "FAIL"})
            return None
        result["checks"].append({"check": label, "status": "STATIC_PASS"})
        return value

    def read(path):
        info = path.stat()
        require(stat.S_ISREG(info.st_mode) and info.st_size <= MAX_INPUT_BYTES, "expected bounded regular input file")
        with path.open("rb") as stream:
            data = stream.read(MAX_INPUT_BYTES + 1)
        require(len(data) <= MAX_INPUT_BYTES, "input grew beyond size limit")
        result["files"][str(path)] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        return data.decode("utf-8")

    def load_hjson():
        try:
            return importlib.import_module("hjson")
        except ImportError as error:
            raise CheckError("configuration error: missing hjson; run with the prepared PLIC venv") from error

    parser = attempt("dependency.hjson", load_hjson)
    inputs = [("data/rv_plic.ipconfig.hjson", check_config), ("data/rv_plic.hjson", check_hjson)]
    if (root / "rv_plic.cfg.hjson").exists() or (root / "rv_plic.cfg.hjson").is_symlink():
        inputs.append(("rv_plic.cfg.hjson", check_config))
    for relative, validator in inputs:
        text = attempt(relative + ".read", lambda relative=relative: read(root / relative))
        if text is not None and parser is not None:
            attempt(relative, lambda text=text, validator=validator:
                    validator(parser.loads(text, object_pairs_hook=unique_object)))
    validators = {"rv_plic_reg_pkg": check_pkg, "rv_plic_reg_top": check_top, "rv_plic": check_core}
    for name in RTL_FILES:
        relative = f"rtl/{name}.sv"
        text = attempt(relative + ".read", lambda relative=relative: read(root / relative))
        if text is not None:
            validator = validators.get(name, lambda code, name=name: check_helper(code, name))
            attempt(relative, lambda text=text, validator=validator: validator(sv_code(text)))
    if dts_path is not None:
        path = Path(dts_path).resolve()
        result["dts"] = {"status": "FAIL", "path": str(path)}
        text = attempt("dts.read", lambda: read(path))
        if text is not None:
            data = attempt("dts", lambda: check_dts(path, text))
            if data is not None:
                result["dts"].update(data)
    result["accepted"] = not result["errors"]
    result["status"] = "STATIC_PASS" if result["accepted"] else "FAIL"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--plic-dir", type=Path, required=True)
    parser.add_argument("--dts", type=Path)
    parser.add_argument("--output", type=Path, help="exclusive-create JSON outside the PLIC input tree")
    args = parser.parse_args(argv)
    result = check_plic(args.plic_dir, args.dts)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        try:
            output, root = args.output.resolve(), args.plic_dir.resolve()
            require(output != root and root not in output.parents, "output must be outside the PLIC input tree")
            require(not args.output.is_symlink(), "output must not be a symlink")
            require(args.dts is None or output != args.dts.resolve(), "output must not overwrite DTS")
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(payload)
        except (OSError, CheckError) as error:
            print(f"cannot save PLIC report: {error}", file=sys.stderr)
            return 2
    print(payload, end="")
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
