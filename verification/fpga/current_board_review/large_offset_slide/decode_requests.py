#!/usr/bin/env python3
"""Inspect already captured request geometry without another RTL simulation."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'comparison'))
from decode_cycle import vcd

ARA = 'ara_tb.dut.i_ara_soc.i_system.i_ara'
LANE = ARA + '.gen_lanes[0].i_lane.i_lane_sequencer'
events = iter(vcd(HERE / 'capture01/selected.vcd'))
_, decl = next(events)
fields = {'clk': 'ara_tb.clk', 'valid': ARA + '.ara_req_valid',
          'push': LANE + '.operand_request_push'}
for field in ('op', 'vl', 'vstart', 'vd', 'emul', 'vtype.vsew', 'vtype.vlmul',
              'vm', 'eew_vmask', 'verify_arch_insn'):
    fields['req_' + field] = ARA + '.ara_req.' + field
for field in ('id', 'vs', 'eew', 'vl', 'vstart', 'is_slide', 'scale_vl',
              'vtype.vsew', 'hazard'):
    fields['mask_' + field] = LANE + '.operand_request[6].' + field
codes = {key: decl[name]['code'] for key, name in fields.items()}
previous = None
for time, before, after in events:
    if before.get(codes['clk']) != '0' or after.get(codes['clk']) != '1':
        continue
    row = {}
    for key, code in codes.items():
        bits = before.get(code, 'x')
        row[key] = int(bits, 2) if set(bits) <= set('01') else None
    if (row['valid'] or (row['push'] or 0) & 64) and row != previous:
        print(json.dumps(dict(time_ns=time / 10000, **row)))
    previous = row
