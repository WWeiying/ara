#!/usr/bin/env python3
"""Assert the specific M5->M6 causal chain; no whole-run acceptance."""
import json
from pathlib import Path
import re
import time
from acquire import HERE, ART, OWNER, files, sha, save

read = lambda p: json.loads(p.read_text())
wave = read(HERE/'wave_findings02.json')
ledger = read(HERE/'ledger.json')
acquisition = read(HERE/'acquisition.json')
image_path = Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image/image.json')
image = read(image_path)
assert read(ART/'inputs.json')['simv'] == dict(path=image['simv'], image_sha256=image['files'])
assert read(ART/'command.json')['command'][0] == image['simv']
old_art = OWNER/'vcs_candidate05_plan01/prepared02/pilot/tests/d32m2_i64_fault_ov1'
assert sha(ART/'input.elf') == sha(old_art/'input.elf')
for path, digest in acquisition['pins'].items():
    assert sha(Path(path)) == digest, path
later_source = dict(observed_at=time.time(), files=files())
recovery = read(HERE/'recovery_export.json')
assert recovery['original_and_copied_inputs_unchanged']
assert sha(HERE/'recovered.fsdb') == recovery['recovered_sha256']
assert wave['clock_period_ticks'] == [10000]

decode = next(e for e in wave['settled_dispatcher_transitions'] if e['ns'] == 368512.5)
d = decode['settled']
assert (d['csr_vstart_q'], d['indexed_mixed_vs2_layout'], d['reshuffle_req_d'],
        d['eew_q[4]'], d['eew_q[5]'], d['state_name']) == (15,1,2,2,3,'NORMAL_OPERATION')
assert decode['req']['op_name']=='VLXE' and decode['req']['vs2']==decode['req']['vd']==4
edges = {e['cycle']:e for e in wave['csv_tied_edges']}
for cycle in (368501,368519,368540,368557):
    assert len(edges[cycle]['allocated']) == 1 and edges[cycle]['seq_valid'] == 1
for cycle in (368516,368536,368555):
    assert len(edges[cycle]['done']) == 1
src, cap, dst, target = [edges[c]['req'] for c in (368501,368519,368540,368557)]
assert (src['op_name'],src['vs2'],src['vd'],src['eew_vs2'],src['vtype.vsew']) == ('VSLIDEDOWN',4,4,2,3)
assert cap['source_snapshot_capture']==1 and cap['use_vd']==0 and cap['eew_vs2']==3
assert (dst['op_name'],dst['vs2'],dst['vd'],dst['eew_vs2'],dst['vtype.vsew']) == ('VSLIDEDOWN',4,4,3,2)
assert (target['op_name'],target['vstart'],target['vl'],target['old_eew_vs2'],
        target['source_snapshot_replay_vs2'],target['vtype.vsew']) == ('VLXE',15,32,3,1,2)
captures = [e for e in wave['capture_edges'] if 368500 < e['ns'] < 368600]
assert len(captures)==32 and {(e['lane'],e['index']) for e in captures} == {(l,i) for l in range(4) for i in range(8)}
assert min(e['cycle'] for e in captures) > 368516 and max(e['cycle'] for e in captures) < 368540
saved4 = sorted([e for e in captures if e['index']==4], key=lambda e:e['lane'])
expected = ['0x17000','0x4000','0x11000','0x1e000']
assert [e['data'] for e in saved4] == expected
replay4 = sorted([e for e in wave['replay_edges'] if e['cycle']==368561], key=lambda e:e['lane'])
assert len(replay4)==4 and [e['data'] for e in replay4]==expected
assert all(e['index']==4 and e['queue_valid']==1 and e['vrf_valid']==0 and
           e['metadata']['source_snapshot_replay']==1 and e['metadata']['vew']==3 and
           e['dispatcher']['eew_q[4]']==2 for e in replay4)
address_input = next(e for e in wave['addrgen_window'] if e['cycle']==368562)
v = address_input['values']
assert [hex(v[f'addrgen_operand_i[{i}]']) for i in range(4)] == expected
assert v['addrgen_operand_valid_i']==15 and v['idx_vaddr']==0x17000
assert (v['pe_req_q.old_eew_vs2'],v['pe_req_q.source_snapshot_replay_vs2'],v['pe_req_q.vstart']) == (3,1,15)
correct_mmu = next(e for e in wave['mmu_edges'] if e['cycle']==368576)
assert correct_mmu['values']['mmu_vaddr_o']==0x40017000 and correct_mmu['values']['mmu_req_o']==1
mmu_fault = next(e for e in wave['addrgen_window'] if e['cycle']==368588)
assert (mmu_fault['values']['mmu_exception_i.valid'],mmu_fault['values']['mmu_exception_i.cause'],
        mmu_fault['values']['mmu_exception_i.tval']) == (1,13,0x40017000)
ag_fault = next(e for e in wave['addrgen_window'] if e['cycle']==368589)
assert (ag_fault['values']['addrgen_exception_o.valid'],ag_fault['values']['addrgen_exception_o.tval'],
        ag_fault['values']['addrgen_exception_vstart_o']) == (1,0x40017000,16)
csr = ledger['faults'][16]
assert not csr['mismatch_fields'] and csr['csr']['mtval']==0x40017000 and csr['csr']['vstart']==16
assert all(c['equal'] for c in csr['checks']) and csr['mret_cycle']==369154
old = read(OWNER/'failure_analysis01/ledger.json')['fault_handlers'][16]
assert old['csr']['mtval']==0x400040017000
write, = [e for e in wave['vldu_write_edges'] if 368557 <= e['cycle'] <= 368593]
w = write['values']
assert write['cycle']==368588 and write['req'] & write['gnt']==15
assert [w[f'ldu_result_be_o[{i}]'] for i in range(4)] == [0,0,0,240]
assert [w[f'ldu_result_addr_o[{i}]'] for i in range(4)] == [17]*4
pkg = Path(image['snapshot'])/'sources/hardware/include/ara_pkg.sv'
text = pkg.read_text().split('      4: unique case (ew)',1)[1].split('rvv_pkg::EW32: begin',1)[1].split('end',1)[0]
shuffle = {int(a):int(b) for a,b in re.findall(r'idx\[(\d+)\]\s*=\s*(\d+)',text)}
assert len(shuffle)==32
# vaddr(v4,4,VLEN1024)=16; address17 is the next32-byte group.
physical_bytes = [3*8+b for b in range(8) if w['ldu_result_be_o[3]'] & (1<<b)]
logical_bytes = [32+next(k for k,v in shuffle.items() if v==b) for b in physical_bytes]
assert logical_bytes == [60,61,62,63] and {b//4 for b in logical_bytes} == {15}

# Further prune the already bounded export to exactly the analyzer's516 names.
source = HERE/'recovered_focus.vcd'
destination = HERE/'focused516.vcd'
decls = wave['declarations']
codes = {d['code'] for d in decls.values()}
scopes, in_header, count = [], True, 0
prefix = 'ara_tb.dut.i_ara_soc.i_system.i_ara.'
with source.open() as stream, destination.open('x') as out:
    for line in stream:
        s = line.split()
        keep = True
        if in_header:
            if s and s[0]=='$scope': scopes.append(s[2])
            elif s and s[0]=='$upscope': scopes.pop()
            elif s and s[0]=='$var':
                name = '.'.join(scopes+[s[4]]).removeprefix(prefix)
                if len(s)>6: name += re.sub(r'\[\d+:\d+\]$', '', s[5])
                keep = name in decls
                count += keep
            elif s and s[0]=='$enddefinitions': in_header=False
        elif s and s[0][0] in 'bB': keep = s[1] in codes
        elif s and s[0][0] in '01xXzZ': keep = s[0][1:] in codes
        if keep: out.write(line)
assert count == 516
pins = {str(p):sha(p) for p in (HERE/'acquisition.json', HERE/'recovery_export.json', HERE/'ledger.json',
    HERE/'wave_findings02.json', source, destination, image_path, pkg, Path(__file__),
    HERE/'analyze_wave.py', HERE/'ledger.py', HERE/'export_recovered.py',
    OWNER/'failure_analysis01/ledger.json', OWNER/'reference03/fixture.c')}
pins.update(acquisition['pins'])
save(HERE/'finding.json', dict(status='MEASURED_M6_OLD_FAILURE_PATH_CORRECT_IN_BOUNDED_WINDOW',
    exact_same_M5_M6_private_ELF_sha256=sha(ART/'input.elf'), full50_acceptance=False,
    image_sha256=sha(image_path), profile_disabled_flushed_writer_open_at_acquisition=True,
    acquisition_provenance=dict(private_raw_copies_still_match_acquisition=True,
        original_unchanged_during_acquisition_and_recovery_export=True,
        later_original_observation=later_source,
        later_original_matches_acquisition=later_source['files']==acquisition['before'],
        note='Original writer-owned container later changed; private raw copies remain unchanged. Recovery merged copied sidecars into a derived container, not invented samples. No terminal/service inference.'),
    wave_units='100fs', clock_period_ns=1, pre_edge_ns_equals_csv_cycle_plus=15.5,
    decode_settled=decode, maintenance_allocation_and_done=[edges[c] for c in (368501,368516,368519,368536,368540,368555,368557)],
    capture_word4=saved4, replay_word4=replay4, addrgen_input=address_input,
    correct_mmu=correct_mmu, mmu_fault=mmu_fault, addrgen_fault=ag_fault, architectural_csr=csr,
    old_M5_mtval=hex(old['csr']['mtval']), M6_mtval=hex(csr['csr']['mtval']),
    prestart=dict(measured_write=write, static_frozen_shuffle_logical_bytes=logical_bytes,
        architectural_elements=[15], prestart_elements0_through14_enabled=False,
        scope='Only original VLXE data write, not maintenance writes; no claim of full50 validation'),
    evidence_boundary='Final settled reshuffle_req_d=010 is measured. Earlier procedural assignments inside always_comb are static reconstruction, not independent waveform observations. Seq CSV allocation is not ara_req ready response. idx_op_cnt is remaining elements, not element number.',
    evidence_pins=pins, no_DUT_started=True, no_original_file_writes=True))
print(json.dumps(dict(status='BOUNDED_PATH_CONFIRMED', selected_signals=count,
    focus_bytes=destination.stat().st_size, M6_mtval='0x40017000', M5_mtval='0x400040017000',
    source_done=368516, capture_done=368536, vd_done=368555, original_allocation=368557,
    prestart_write_elements=[15]),indent=2))
