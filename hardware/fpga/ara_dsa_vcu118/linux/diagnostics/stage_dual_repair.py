#!/usr/bin/env python3
"""Repair a verified combined package without importing unrelated working edits."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from stage_dual_ethernet import replace_once

ADAPTER = 'rtl/cva6/core/cache_subsystem/wt_axi_adapter.sv'
TOP = 'rtl/board/ara_dsa_vcu118.sv'
PROJECT = 'scripts/create_project.tcl'
CLOCK = 'constraints/ddr2_clock.xdc'


def repair(name, data):
    text = data.decode() if name in (ADAPTER, TOP, PROJECT) else None
    if name == ADAPTER:
        text = replace_once(text, 'axi_rd_rdy        = ~invalidate;',
                            'axi_rd_rdy        = ~invalidate & ~inval_valid_i;')
        text = replace_once(text, '// we are not ready when invalidating',
            '// Invalidation owns the D-cache return slot. Backpressure AXI as well,\n'
            '    // otherwise a simultaneous read beat is accepted but never captured.')
        text = replace_once(text,
            '// External invalidation requests (from coprocessor). This is safe as\n'
            '    // there are no other transactions when a coprocessor has pending stores.',
            '// External invalidation can overlap speculative fetches and page walks.\n'
            '    // The shared R channel is held until this return slot is available.')
    elif name == TOP:
        text = replace_once(text, '`ifdef ARA_FPGA_DDR2\n  output logic c1_ddr4_act_n,',
            '`ifdef ARA_FPGA_DDR2\n  input logic c2_sys_clk_p, c2_sys_clk_n,\n  output logic c1_ddr4_act_n,')
        text = replace_once(text, '  if (1) begin : gen_ddr2\n',
            '  if (1) begin : gen_ddr2\n'
            '    wire c2_sys_clk;\n'
            "    // U21 Q1 is local to C2's SLR; C1's reference cannot clock this MIG.\n"
            '    IBUFDS #(.IBUF_LOW_PWR("FALSE")) i_bufds_c2_clk (\n'
            '      .I(c2_sys_clk_p), .IB(c2_sys_clk_n), .O(c2_sys_clk)\n'
            '    );\n')
        text = replace_once(text, '.dram_clk_i(sys_clk), .fabric_ready_o(dram_ready[1])',
                                  '.dram_clk_i(c2_sys_clk), .fabric_ready_o(dram_ready[1])')
    elif name == PROJECT:
        anchor = 'add_files -fileset constrs_1 -norecurse [file join $package_root constraints board.xdc]\n'
        text = replace_once(text, anchor, anchor +
            'if {$fpga_profile in {dual_ddr dual_ddr_ethernet}} {\n'
            '    add_files -fileset constrs_1 -norecurse [file join $package_root constraints ddr2_clock.xdc]\n}\n')
    return text.encode() if text is not None else data


def stage(source, target):
    source = source.resolve(strict=True)
    target = target.absolute()
    if target.exists() or source in target.parents:
        raise ValueError('New output outside source required')
    digest = lambda data: hashlib.sha256(data).hexdigest()
    inventory = (source / 'SHA256SUMS').read_bytes()
    files, changes = {}, {}
    for row in inventory.decode().splitlines():
        expected, name = row.split('  ', 1)
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name or name in files:
            raise ValueError('Unsafe/duplicate inventory entry')
        before = (source / name).read_bytes()
        if digest(before) != expected:
            raise ValueError('Source hash mismatch: ' + name)
        after = repair(name, before)
        files[name] = after
        if before != after:
            changes[name] = {'before': digest(before), 'after': digest(after)}
    if set(changes) != {ADAPTER, TOP, PROJECT} or 'provenance/dual_ethernet.json' not in files:
        raise ValueError('Expected the original combined dual-DDR package')
    if CLOCK in files:
        raise ValueError('Clock repair already present')
    files[CLOCK] = (Path(__file__).resolve().parents[2] / CLOCK).read_bytes()
    changes[CLOCK] = {'before': None, 'after': digest(files[CLOCK])}
    record = {'source': str(source), 'source_inventory': digest(inventory),
              'changes': changes, 'profile': 'dual_ddr_ethernet',
              'board_modified': False, 'hardware_validated': False}
    files['provenance/dual_inval_clock_fix.json'] = (json.dumps(record, indent=2)+'\n').encode()
    target.mkdir(parents=True)
    for name, data in files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (target/'SHA256SUMS').write_text(''.join(f'{digest(data)}  {name}\n' for name,data in sorted(files.items())))
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('target', type=Path)
    a = p.parse_args()
    stage(a.source, a.target)
