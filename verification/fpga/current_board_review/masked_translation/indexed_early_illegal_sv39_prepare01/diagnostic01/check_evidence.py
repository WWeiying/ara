#!/usr/bin/env python3
"""Check decoded evidence, not architecture or a repaired design."""
import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
data = json.loads((HERE/'analysis.json').read_text())
rows = []
with (HERE/'cycles.csv').open() as f:
    for row in csv.DictReader(f):
        rows.append({k:float(v) if k == 'time_ns' else int(v) if v else None for k,v in row.items()})
by_cycle = {r['cycle']:r for r in rows}
assert all(r['time_ns']-r['cycle'] == 15.5 for r in rows)
error = by_cycle[79692]
assert error['ag_idx_final_vaddr_q'] == 0x40000011
for k,v in {'ag_idx_op_error_d':1, 'ag_mmu_req_o':1, 'ag_mmu_valid_i':0,
            'lsu_genblk3.mmu_state_q':0, 'lsu_genblk3.mmu_state_d':1,
            'lsu_lsu_valid_i':0, 'lsu_lsu_ready_o':1, 'lsu_translation_req':0}.items():
    assert error[k] == v, (k,error[k])
lock = [r for r in rows if r['cycle'] >= 79693]
for r in lock:
    for k,v in {'lsu_genblk3.mmu_state_q':1, 'lsu_genblk3.mmu_state_d':1,
                'ag_mmu_req_o':0, 'ag_mmu_valid_i':0, 'lsu_translation_req':0,
                'lsu_translation_valid':0, 'ag_axi_addrgen_state_q':0}.items():
        assert r[k] == v, (r['cycle'],k,r[k])
assert by_cycle[79693]['ag_addrgen_exception_o.cause'] == 6
assert by_cycle[79693]['ag_addrgen_exception_o.tval'] == 0x40000011
assert by_cycle[79693]['ag_addrgen_exception_o.valid'] == 1
assert by_cycle[79706]['ara_ara_idle'] == 1
assert by_cycle[79713]['ara_lsu_ex_flush_done'] == 1
blocked = [r for r in rows if r['cycle'] >= 79736]
for r in blocked:
    for k,v in {'lsu_lsu_bypass_i.status_cnt_q':1, 'lsu_lsu_bypass_i.empty':0,
                'lsu_ld_vaddr':0x80008078, 'lsu_ld_valid_i':0,
                'lsu_i_load_unit.state_q':0, 'lsu_i_load_unit.valid_i':0,
                'lsu_cva6_translation_req':0, 'ara_ara_idle':1, 'ara_store_pending':0,
                'stu_vinsn_queue_q.commit_cnt':0, 'stu_vinsn_queue_q.issue_cnt':0,
                'sys_inval_valid':0, 'lsu_stall_st_pending_i':0}.items():
        assert r[k] == v, (r['cycle'],k,r[k])
    assert all(r['stu_vinsn_queue_q.pending_b[%d]'%i] == 0 for i in range(4))
for interface in ('axi','delayed'):
    for channel,cycle in (('aw',79697),('w',79698),('b',79703)):
        assert [r['cycle'] for r in data['handshakes'][interface][channel]] == [cycle]
    assert data['handshakes'][interface]['aw'][0][interface+'_aw.addr'] == 0x80003008
    assert data['handshakes'][interface]['b'][0][interface+'_b.resp'] == 0
assert data['csv_byte_identical'] is True
complete = json.loads((HERE/'complete.json').read_text())
assert complete['returncode'] == 0 and complete['pins_unchanged'] and complete['planned_stop_observed']
assert not complete['timed_out'] and not complete['architectural_acceptance']
with (HERE/'checked_evidence.json').open('x') as f:
    json.dump(dict(status='MEASURED_ORPHAN_MMU_REQUEST_LOCK_NOT_ARCHITECTURAL_PASS',
        rows=len(rows), locked_cycles=len(lock), blocked_load_cycles=len(blocked),
        cycle_to_ns_offset=15.5, direct_lsu_control_structs_captured=False,
        input_pins=len(json.loads((HERE/'invocation.json').read_text())['input_pins']),
        evidence={name:sha(HERE/name) for name in ('analysis.json','cycles.csv','complete.json',
                   'invocation.json','diagnostic.fsdb','selected.vcd','decode.py','check_evidence.py')}), f, indent=2)
print('EVIDENCE_CHECK_PASS', len(lock), len(blocked))
