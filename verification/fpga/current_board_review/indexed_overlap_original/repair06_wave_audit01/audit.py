#!/usr/bin/env python3
"""Independent offline audit of the frozen, bounded M6 waveform evidence."""
import csv
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "repair06_wave_review01"
FROZEN = Path("/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/hardware")
PREFIX = "ara_tb.dut.i_ara_soc.i_system.i_ara."


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for data in iter(lambda: stream.read(1048576), b""):
            result.update(data)
    return result.hexdigest()


def read(name):
    return json.loads((SOURCE / name).read_text())


def parse_vcd(path, selected=None):
    scopes, codes, names, scale, blocks = [], {}, set(), [], []
    tick, changes = None, {}
    with path.open() as stream:
        for line in stream:
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "$scope":
                scopes.append(parts[2])
            elif parts[0] == "$upscope":
                scopes.pop()
            elif parts[0] == "$var":
                name = ".".join(scopes + [parts[4]])
                if name.startswith(PREFIX):
                    name = name[len(PREFIX):]
                if len(parts) > 6:
                    name += re.sub(r"\[\d+:\d+\]$", "", parts[5])
                if selected is None or name in selected:
                    assert name not in names, name
                    names.add(name)
                    codes.setdefault(parts[3], []).append(name)
            scale.append(line)
            if parts[0] == "$enddefinitions":
                break
        assert re.search(r"\$timescale\s+100fs\s+\$end", "".join(scale))
        for line in stream:
            text = line.strip()
            if not text:
                continue
            if text.startswith("#"):
                if tick is not None:
                    blocks.append((tick, changes))
                tick, changes = int(text[1:]), {}
            elif text[0] in "bB":
                value, code = text[1:].split()
                value = int(value, 2) if set(value) <= {"0", "1"} else value
                for name in codes.get(code, []):
                    changes[name] = value
            elif text[0] in "01xXzZ":
                value = int(text[0]) if text[0] in "01" else text[0]
                for name in codes.get(text[1:], []):
                    changes[name] = value
        if tick is not None:
            blocks.append((tick, changes))
    return names, blocks


def main():
    finding = read("finding.json")
    acquisition = read("acquisition.json")
    recovery = read("recovery_export.json")
    wave = read("wave_findings02.json")
    pins = dict(finding["evidence_pins"])
    pins.update(wave["pins"])
    pins.update(acquisition["pins"])
    pins[str(SOURCE / "README.md")] = "a5ab9d64f88d1884d790f2d5eeb4c89953a82ab01befcdbee4e3d81cd5244e6f"
    pins[str(SOURCE / "finding.json")] = "70c3d8d2532e7093e668fd5c49e79f268766e02efab92c190cb5b80d42b1b233"
    pins[str(SOURCE / "recovered.fsdb")] = recovery["recovered_sha256"]
    pins[str(FROZEN / "src/ara_sequencer.sv")] = digest(FROZEN / "src/ara_sequencer.sv")
    pins[str(FROZEN / "tb/ara_commit_monitor.sv")] = digest(FROZEN / "tb/ara_commit_monitor.sv")
    for path, expected in pins.items():
        assert digest(path) == expected, path
    assert len(acquisition["before"]) == 13
    assert acquisition["before"] == acquisition["after"] == acquisition["after_export"]
    assert recovery["recovery_returncode"] == recovery["returncode"] == 0
    assert recovery["original_max_ticks"] == recovery["recovered_max_ticks"] == 10000000000
    assert "-del_src" not in recovery["recovery_command"] and "-cp" not in recovery["recovery_command"]
    assert recovery["recovery_command"][-2:] == ["-o", "recovered.fsdb"]
    names, filtered = parse_vcd(SOURCE / "focused516.vcd")
    full_names, full = parse_vcd(SOURCE / "recovered_focus.vcd", names)
    assert len(names) == 516 and names == full_names and filtered == full
    assert 3677000000 <= full[0][0] <= full[-1][0] <= 3693000000 < 10000000000
    state, edges, settled, clock_ticks = {}, {}, {}, []
    cycle_name = next(name for name in names if name.endswith("i_ara_commit_monitor.cycle_q"))
    for tick, changes in full:
        if state.get("ara_tb.clk") == 0 and changes.get("ara_tb.clk") == 1:
            cycle = state[cycle_name]
            assert tick == (cycle * 10000 + 155000)
            clock_ticks.append(tick)
            edges[cycle] = dict(state)
        state.update(changes)
        if tick == 3685125000:
            settled = dict(state)
    assert {b - a for a, b in zip(clock_ticks, clock_ticks[1:])} == {10000}
    assert [settled["i_dispatcher." + name] for name in (
        "csr_vstart_q", "indexed_mixed_vs2_layout", "reshuffle_req_d", "eew_q[4]", "eew_q[5]")] == [15, 1, 2, 2, 3]
    expected_words = [0x17000, 0x4000, 0x11000, 0x1E000]
    capture = []
    for cycle, values in edges.items():
        if not 368516 < cycle < 368540:
            continue
        for lane in range(4):
            p = "gen_lanes[%d].i_lane." % lane
            if values[p + "source_snapshot_capture_q"] == 1 and values[p + "vrf_operand_valid"] & 256:
                capture.append([cycle, lane, values[p + "source_snapshot_capture_index_q"], values[p + "vrf_operand[8]"]])
    assert len(capture) == 32 and {(lane, index) for _, lane, index, _ in capture} == {(lane, index) for lane in range(4) for index in range(8)}
    for lane in range(4):
        p = "gen_lanes[%d].i_lane." % lane
        assert next(data for _, l, index, data in capture if l == lane and index == 4) == expected_words[lane]
        values = edges[368561]
        assert values[p + "source_snapshot_replay_valid"] & 256
        assert values[p + "source_snapshot_replay_index[8]"] == 4
        assert values[p + "operand_queue_input[8]"] == expected_words[lane]
        assert values[p + "operand_queue_input_valid"] & 256 and not values[p + "vrf_operand_valid"] & 256
        assert values[p + "i_operand_requester.requester_metadata_q[8].vew"] == 3
        assert values[p + "i_operand_requester.requester_metadata_q[8].source_snapshot_replay"] == 1
    assert edges[368561]["i_dispatcher.eew_q[4]"] == 2
    addr = "i_vlsu.i_addrgen."
    values = edges[368562]
    assert [values[addr + "addrgen_operand_i[%d]" % i] for i in range(4)] == expected_words
    assert [values[addr + name] for name in ("addrgen_operand_valid_i", "addrgen_operand_ready_o", "idx_vaddr", "pe_req_q.old_eew_vs2", "pe_req_q.vstart", "pe_req_q.source_snapshot_replay_vs2")] == [15, 0, 0x17000, 3, 15, 1]
    assert edges[368576][addr + "mmu_req_o"] == 1 and edges[368576][addr + "mmu_vaddr_o"] == 0x40017000
    assert [edges[368588][addr + name] for name in ("mmu_exception_i.valid", "mmu_exception_i.cause", "mmu_exception_i.tval")] == [1, 13, 0x40017000]
    assert [edges[368589][addr + name] for name in ("addrgen_exception_o.valid", "addrgen_exception_o.tval", "addrgen_exception_vstart_o")] == [1, 0x40017000, 16]
    write = edges[368588]
    ldu = "i_vlsu.i_vldu."
    assert write[ldu + "ldu_result_req_o"] & write[ldu + "ldu_result_gnt_i"] == 15
    be = [write[ldu + "ldu_result_be_o[%d]" % i] for i in range(4)]
    assert be == [0, 0, 0, 240]
    assert [write[ldu + "ldu_result_addr_o[%d]" % i] for i in range(4)] == [17] * 4
    pkg = (FROZEN / "include/ara_pkg.sv").read_text()
    body = pkg.split("      4: unique case (ew)", 1)[1].split("rvv_pkg::EW32: begin", 1)[1].split("end", 1)[0]
    shuffle = {int(a): int(b) for a, b in re.findall(r"idx\[(\d+)\]\s*=\s*(\d+)", body)}
    logical = [32 + next(a for a, b in shuffle.items() if b == 24 + byte) for byte in range(8) if be[3] & (1 << byte)]
    assert logical == [60, 61, 62, 63]
    registers, events, csr_reads, checks = {i: 0 for i in range(32)}, [], {}, []
    csr_names = {0x342: "mcause", 0x341: "mepc", 0x343: "mtval", 8: "vstart", 0xC20: "vl", 0xC21: "vtype", 3: "fcsr", 15: "vcsr"}
    symbols = json.loads((HERE.parent / "reference03/d32m2_i64_fault_ov1/soc.symbols.json").read_text())
    with (SOURCE / "inputs/commit_through_cycle600000.csv").open() as stream:
        for row in csv.DictReader(stream):
            cycle = int(row["cycle"])
            if row["event"] in ("uop_alloc", "uop_done") and 368497 <= cycle <= 368590:
                events.append([cycle, row["event"], int(row["order"]), int(row["port"])])
            if row["event"] != "retire":
                continue
            pc, insn = int(row["pc"], 16), int(row["insn"], 16)
            rd, data = int(row["rd"]), int(row["rd_wdata"], 16)
            if 368602 <= cycle <= 369154:
                if insn & 127 == 0x73 and (insn >> 12) & 7 in (2, 3) and (insn >> 15) & 31 == 0 and rd and insn >> 20 in csr_names:
                    csr_reads[csr_names[insn >> 20]] = [cycle, data]
                if pc == symbols["check"]:
                    checks.append([cycle, registers[10], registers[11]])
                    assert registers[10] == registers[11]
                if pc == symbols["io_retry_mret"]:
                    assert cycle == 369154 and insn == 0x30200073
            if not int(row["trap"]) and rd:
                registers[rd] = data
    assert [item[:2] for item in events[:7]] == [[368501, "uop_alloc"], [368516, "uop_done"], [368519, "uop_alloc"], [368536, "uop_done"], [368540, "uop_alloc"], [368555, "uop_done"], [368557, "uop_alloc"]]
    for cycle in (368501, 368519, 368540, 368557):
        assert edges[cycle]["i_sequencer.ara_req_valid_i"] == 1
    for cycle in (368516, 368536, 368555):
        assert edges[cycle]["i_sequencer.verify_vinsn_done"] & 1
    assert {name: value for name, (_, value) in csr_reads.items()} == dict(mcause=13, mepc=0x80000D64, mtval=0x40017000, vstart=16, vl=32, vtype=17, fcsr=117, vcsr=5)
    assert len(checks) == 9 and [369018, 0x40017000, 0x40017000] in checks
    result = dict(status="BOUNDED_WAVE_INDEPENDENTLY_CONFIRMED_NOT_FULL50", pins_verified=len(pins),
        raw_family_files=13, units="100fs", clock_ticks=10000, preedge_csv_offset_ns=15.5,
        selected_signal_samples_identical=True, capture_count=32, capture_cycles=[min(x[0] for x in capture), max(x[0] for x in capture)],
        uop_events=events, replay_words=expected_words, mmu_cycle=368576, mmu_va="0x40017000",
        csr_reads=csr_reads, checks=checks, data_write_logical_bytes=logical,
        old_vd_contents_independently_sampled=False, full50_acceptance=False, service_exit_audited=False,
        no_DUT_or_RTL_actions=True, pins=pins)
    with (HERE / "audit.json").open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({key: value for key, value in result.items() if key != "pins"}))


if __name__ == "__main__":
    main()
