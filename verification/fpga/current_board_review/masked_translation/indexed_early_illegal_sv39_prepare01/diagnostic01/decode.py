#!/usr/bin/env python3
"""Read the closed capture; sample inputs immediately before rising edges."""
import csv
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'comparison'))
from decode_cycle import vcd

TOP = 'ara_tb.dut.i_ara_soc.i_system'
ARA = TOP + '.i_ara'
AG = ARA + '.i_vlsu.i_addrgen'
LSU = TOP + '.i_ariane.ex_stage_i.lsu_i'
fields = {'clk': 'ara_tb.clk', 'cycle': TOP + '.i_ara_commit_monitor.cycle_q'}
for prefix, scope, names in (
    ('ag_', AG, ('state_q', 'axi_addrgen_state_q', 'idx_op_error_d', 'idx_op_error_q',
        'idx_final_vaddr_q', 'idx_vaddr_valid_q', 'mmu_req_o', 'mmu_req_d', 'mmu_valid_i',
        'addrgen_exception_o.valid', 'addrgen_exception_o.cause', 'addrgen_exception_o.tval')),
    ('ara_', ARA, ('ara_idle', 'store_pending', 'lsu_ex_flush_lane', 'lsu_ex_flush_done',
        'i_dispatcher.lsu_ex_state_q')),
    ('stu_', ARA + '.i_vlsu.i_vstu', ('exception_pending_q', 'store_complete_o',
        'vinsn_queue_q.issue_cnt', 'vinsn_queue_q.commit_cnt',
        'vinsn_queue_q.pending_b[0]', 'vinsn_queue_q.pending_b[1]',
        'vinsn_queue_q.pending_b[2]', 'vinsn_queue_q.pending_b[3]')),
    ('lsu_', LSU, ('genblk3.mmu_state_q', 'genblk3.mmu_state_d', 'lsu_ready_o', 'lsu_valid_i',
        'translation_req', 'translation_valid', 'cva6_translation_req', 'cva6_translation_valid',
        'mmu_vaddr', 'ld_valid_i', 'ld_vaddr', 'pop_ld', 'stall_st_pending_i', 'store_buffer_empty',
        'i_load_unit.valid_i', 'i_load_unit.vaddr_o', 'i_load_unit.state_q', 'i_load_unit.valid_o',
        'lsu_bypass_i.status_cnt_q', 'lsu_bypass_i.empty')),
    ('sys_', TOP, ('inval_valid', 'inval_ready')),
):
    fields.update({prefix + n: scope + '.' + n for n in names})
for name, req, resp in (('axi', 'ara_axi_req', 'ara_axi_resp'),
                        ('delayed', 'ara_axi_req_delayed', 'ara_axi_resp_delayed'),
                        ('cpu_axi', 'ariane_axi_req', 'ariane_axi_resp')):
    for n in ('aw_valid', 'aw.addr', 'aw.len', 'aw.id', 'w_valid', 'w.last', 'b_ready', 'ar_valid', 'ar.addr'):
        fields[name + '_' + n] = TOP + '.' + req + '.' + n
    for n in ('aw_ready', 'w_ready', 'b_valid', 'b.id', 'b.resp', 'ar_ready'):
        fields[name + '_' + n] = TOP + '.' + resp + '.' + n

events = iter(vcd(HERE / 'selected.vcd'))
tag, declarations = next(events)
assert tag == 'declarations'
assert not set(fields.values()) - set(declarations), set(fields.values()) - set(declarations)
codes = {name: declarations[path]['code'] for name, path in fields.items()}
assert '100fs' in (HERE / 'selected.vcd').open().read(256)
rows = []
for tick, before, after in events:
    if before.get(codes['clk']) != '0' or after.get(codes['clk']) != '1':
        continue
    row = {'time_ns': tick / 10000}
    for name, code in codes.items():
        bits = before.get(code, 'x')
        row[name] = int(bits, 2) if set(bits) <= {'0', '1'} else None
    rows.append(row)
assert len(rows) == 4000, len(rows)
with (HERE / 'cycles.csv').open('x') as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
keys = ['ag_idx_op_error_d', 'ag_mmu_req_o', 'ag_mmu_valid_i',
        'lsu_genblk3.mmu_state_q', 'lsu_genblk3.mmu_state_d',
        'lsu_translation_req', 'lsu_translation_valid', 'ag_axi_addrgen_state_q',
        'ara_ara_idle', 'ara_store_pending', 'ara_lsu_ex_flush_lane', 'ara_lsu_ex_flush_done',
        'lsu_lsu_bypass_i.status_cnt_q', 'lsu_ld_valid_i', 'lsu_ld_vaddr']
transitions = []
prev = None
for r in rows:
    state = [r[k] for k in keys]
    if prev != state:
        transitions.append(r)
    prev = state
handshakes = {}
for name in ('axi', 'delayed', 'cpu_axi'):
    handshakes[name] = {}
    for channel, valid, ready in (('aw', 'aw_valid', 'aw_ready'), ('w', 'w_valid', 'w_ready'),
                                   ('b', 'b_valid', 'b_ready'), ('ar', 'ar_valid', 'ar_ready')):
        handshakes[name][channel] = [r for r in rows if r[name+'_'+valid] == r[name+'_'+ready] == 1]
old = HERE.parent / 'vcs_m7_indexed01/run/tests/indexed_prefix_vl3/commit_trace.csv'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
result = dict(rows=len(rows), declaration_count=len(declarations), sampled_fields=fields,
              first=rows[0], last=rows[-1], transitions=transitions, handshakes=handshakes,
              original_csv_sha256=sha(old), diagnostic_csv_sha256=sha(HERE/'commit_trace.csv'),
              csv_byte_identical=sha(old)==sha(HERE/'commit_trace.csv'),
              cycles_sha256=sha(HERE/'cycles.csv'), fsdb_sha256=sha(HERE/'diagnostic.fsdb'),
              vcd_sha256=sha(HERE/'selected.vcd'))
with (HERE/'analysis.json').open('x') as f:
    json.dump(result, f, indent=2)
for r in transitions:
    if 79600 <= r['cycle'] <= 79800:
        print(json.dumps({k:r[k] for k in ['cycle','time_ns','ag_idx_final_vaddr_q']+keys}))
print('BYTE_IDENTICAL_CSV', result['csv_byte_identical'])
print('LAST', json.dumps({k:rows[-1][k] for k in ['cycle','time_ns']+keys}))
print('AXI_COUNTS', {n:{c:len(v) for c,v in s.items()} for n,s in handshakes.items()})
