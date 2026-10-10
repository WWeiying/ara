"""Exact fixture-specific defined-byte qualification; no runner/comparator edits."""
import argparse
import json
from pathlib import Path
import qualify_operand_mask_data_timeout_offline as q
import prepare_operand_mask_data_02_offline_admission as p
import coverage_bitmap_delta as bitmap

MASK_SITES = (13, 28, 43, 58)
DEST_SITES = (3,5,6,7,8,11,12,13,15,18,20,21,22,23,26,27,28,30,
              33,35,36,37,38,41,42,43,45,48,50,51,52,53,56,57,58,60)


def summary_gate(raw):
    q.need(raw['status'] == 'PASS' and raw['first_mismatch'] is None and
           raw['compared_instructions'] == 36 and raw['compared_bytes'] == 27200 and
           raw['skipped_unknown_bytes'] == 64 and raw['non_bit_exact_instructions'] == 0 and
           raw['unobservable_instructions'] == 1 and
           all(raw[k] == [] for k in ('incomplete_requests','unretired_requests','trapped_requests')),
           'Exact full-stream raw comparison contract differs')
    q.need(tuple(r['arch_seq'] for r in raw['instructions']) == DEST_SITES,
           'Destination request universe/order differs')
    for r in raw['instructions']:
        mask = r['arch_seq'] in MASK_SITES
        zero = r['arch_seq'] == 53
        q.need(r['status'] == ('UNOBSERVABLE' if zero else 'PASS') and
               r['mismatch_count'] == 0 and r['first_mismatch'] is None and
               r['skipped_unknown_bytes'] == (16 if mask else 0) and
               r['unknown_write_bytes'] == (16 if mask else 0), 'Unapproved unknown/result site')
        if mask or zero:
            q.need(int(r['instruction'],16) == (0x6a8800d7 if mask else 0x00880c57) and
                   int(r['pc'],16) == (0x800022ea if mask else 0x80002158) and
                   r['compared_bytes'] == (16 if mask else 0), 'Policy site opcode/PC differs')


def byte_gate(seq, register, byte, value, compare_mask, vd):
    if value is None or compare_mask == 0:
        q.need(seq in MASK_SITES and vd == register == 1 and 16 <= byte < 32 and
               compare_mask == 0, 'Unknown actual defined/business byte')
        return False
    return True


def policy_audit(commit_path, vector_path, raw):
    summary_gate(raw)
    vc = q.vc
    lanes, vlen, activities = vc._parse_vector_trace(vector_path)
    starts, retires, traps = vc._parse_architecture_mapping(commit_path)
    arch = vc._map_architecture_retires(starts, retires, traps, allow_incomplete_tail=False)
    commits = vc._spike_from_entry(q.PRE/'spike.trace', 0x80000000)
    mapping = vc._map_spike_commits(arch, commits, allow_incomplete_tail=False)
    q.need((lanes,vlen) == (4,1024) and not traps, 'Geometry/traps differ')
    by_index = {mapping[s]: a for s,a in activities.items() if s in mapping}
    state, unknown, receipts, checked, cursor = {}, {}, [], 0, 0
    for seq in DEST_SITES:
        a, index = activities[seq], mapping[seq]
        while cursor < index:
            before = dict(state)
            state.update(commits[cursor].vector_writes)
            if cursor in by_index:
                vc._advance_unknown_state(unknown,by_index[cursor],commits[cursor],before,vlen)
            cursor += 1
        pre = dict(state)
        c = commits[index]
        state.update(c.vector_writes)
        vc._advance_unknown_state(unknown,a,c,pre,vlen)
        cursor = index+1
        actual = vc._architectural_bytes(a.writes,lanes,vlen)
        tails, active = [], 0
        if seq in MASK_SITES:
            q.need((a.instruction,a.vd,c.vector_sew,c.vector_vl,c.vector_vstart) ==
                   (0x6a8800d7,1,64,128,0), 'Mask active128bit e64 identity differs')
            q.need(set(actual) == {(1,b) for b in range(32)}, 'Mask actual byte extent differs')
        if seq == 53:
            q.need((a.instruction,a.vd,c.vector_sew,c.vector_vl,c.vector_vstart,
                    c.vector_mask_agnostic,c.vector_tail_agnostic) ==
                   (0x00880c57,24,8,1024,0,False,False) and
                   pre[0] & ((1<<1024)-1) == 0 and not actual and
                   all(w.be == 0 for w in a.writes), 'Zero-mask identity not proven')
            expected = q.independent.expected(3)[0]
            q.need(b''.join(pre[r].to_bytes(128,'little') for r in range(24,32)) == expected and
                   all(not unknown.get(r,0) for r in range(24,32)), 'Unknown/wrong preserved destination')
            receipts.append(dict(arch_seq=53,pc='0x80002158',instruction='0x00880c57',
                policy='ZERO_PREDICATE_MU_IDENTITY',defined_bytes=1024,accepted_write_bytes=0,
                reference='Known pre-state v24:v31 + independent phase3 full scalar readback',
                defined_mask='ff '*1024))
        for (reg,byte),(value,write) in sorted(actual.items()):
            mask = vc._architectural_compare_mask(a,reg,byte,vlen,pre,c.vector_writes.keys(),
                c.vector_vl,c.vector_vstart,c.vector_tail_agnostic,c.vector_mask_agnostic)
            mask &= ~((unknown.get(reg,0)>>(8*byte)) & 255)
            if not byte_gate(seq,reg,byte,value,mask,a.vd):
                tails.append(byte)
                continue
            q.need(reg in state and ((value ^ (state[reg]>>(byte*8))) & mask) == 0,
                   'Defined actual byte differs from Spike')
            checked += 1
            active += 1
        if seq in MASK_SITES:
            phase = MASK_SITES.index(seq)
            value = sum(actual[1,b][0]<<(8*b) for b in range(16))
            q.need(tails == list(range(16,32)) and active == 16 and
                   value == q.independent.expected(phase)[1], 'Independent active mask differs')
            receipts.append(dict(arch_seq=seq,pc='0x800022ea',instruction='0x6a8800d7',
                phase=phase,policy='MASK_RESULT_TAIL_AGNOSTIC_NOT_ACTIVE_UNKNOWN',sew=64,lmul=8,
                vl=128,vstart=0,vd='v1',defined_bit_range=[0,127],defined_mask='ff'*16+'00'*16,
                accepted_tail_byte_range=[16,31],defined_bytes=16,tail_bytes=16,
                independent_active_mask_hex=hex(value)))
    q.need(checked == 27200 and len(receipts) == 5, 'Defined byte total differs')
    return dict(status='PASS',policy_sites=receipts,defined_write_bytes=checked,
                unknown_active_bytes=0,agnostic_tail_bytes=64,preserved_identity_bytes=1024,
                raw_comparison_counters_unchanged=True)


def collect(output):
    q.need(output.parent == q.OUT and not output.exists(), 'Fresh independent output required')
    q.need(q.sha(p.PREPARED) == p.PREPARED_SHA, 'Prepared seal drift')
    prepared = json.loads(p.PREPARED.read_bytes())
    state = json.loads((p.RUN/'simulation-status.json').read_bytes())
    p.normal_exit(state)
    native = p.vdb_end(p.RUN/'code.vdb', prepared['command'])
    q.need(q.sha(p.BASE/'admission-manifest.json') == p.BASE_SHA, '762 seal drift')
    base = json.loads((p.BASE/'admission-manifest.json').read_bytes())
    pins = dict(prepared['pins'])
    pins.update(base['input_pins']); pins.update(base['output_pins']); pins.update(native)
    extras = [p.PREPARED,p.BASE/'admission-manifest.json',Path(__file__).resolve(),
        Path(__file__).with_name('test_qualify_operand_mask_data_02_defined.py'),
        Path(q.__file__),Path(p.__file__),Path(bitmap.__file__),Path(q.vc.__file__)]
    extras += [p.RUN/n for n in ('manifest.json','started.json','simulation-status.json',
        'qualification-hold.json','commit_trace.csv','vector_trace.csv','console.log','run.vcs.log')]
    pins.update({str(f):q.sha(f) for f in extras})
    for f,d in pins.items():
        q.need(q.sha(f)==d,'Inherited source/baseline drift: '+f)
    pre = json.loads((q.PRE/'preflight.json').read_bytes())
    prefix,rows,terminal = q.prefix((p.RUN/'commit_trace.csv').read_bytes())
    reference=[]
    for c in q.st.parse_spike_commits(q.PRE/'spike.trace'):
        if not reference and c.pc != 0x80000000: continue
        reference.append(c)
        if (0x80001000,1) in c.memory_accesses: break
    q.need(q.independent.validate(reference)==8256,'Reference independent oracle differs')
    scalar,memory,reads = q.full_scalar(rows,reference,pre['symbols'])
    oracle = q.independent_actual(memory,reads,pre['symbols'])
    vectors = q.table((p.RUN/'vector_trace.csv').read_bytes(),q.VECTOR_FIELDS)
    q.need(all(int(r['cycle'])<=terminal['cycle'] for r in vectors),'Post-terminal vector event')
    life,req,resp = q.lifecycle(rows,vectors)
    console = (p.RUN/'console.log').read_text()
    protocol = q.protocol(console,req,resp,terminal['cycle'])
    final='[ARA_CONTRACT] requests=62 responses=62 exceptions=0 mmu_request_cycles=0 protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0'
    q.need(console.count(final)==1 and console.count('Core Test *** SUCCESS')==1 and
           'Coverage status: End of All Coverages' in console,'Normal final self-check/contract/end missing')
    output.mkdir()
    (output/'commit-prefix.csv').write_bytes(prefix)
    standard = q.st.compare_commit_prefix(q.PRE/'spike.trace',output/'commit-prefix.csv',0x80000000,
        terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
    q.need(standard['status']=='TERMINAL_TOHOST_MATCH','Standard scalar comparison not terminal PASS')
    raw = q.vc.compare_vector_commits(q.PRE/'spike.trace',output/'commit-prefix.csv',p.RUN/'vector_trace.csv',0x80000000)
    policy = policy_audit(output/'commit-prefix.csv',p.RUN/'vector_trace.csv',raw)
    q.save(output/'raw-vector-comparison.json',raw)
    q.save(output/'defined-vector-policy.json',policy)
    q.save(output/'scalar-comparison.json',standard)
    result=dict(status='FULL_ARCHITECTURE_DEFINED_POLICY_QUALIFIED_NORMAL_EXIT_NATIVE_END',
        full_architecture_qualified=True,terminal=terminal,full_scalar=scalar,independent_oracle=oracle,
        full_vector=raw,defined_vector_policy=policy,lifecycle=life,protocol_lastdrain=protocol,
        native_end_pins=native,original_HOLD_preserved=True,raw_unknown_counters_preserved=True,
        simulation_launched=False,consumed_helpers_modified=False,pins=pins)
    q.save(output/'qualification.json',result)
    # Admit only to a new independent successor ledger, never mutate unified reports.
    ledger=(p.BASE/'combined-inputs.txt').read_text().splitlines()
    q.need(len(ledger)==763 and str(p.RUN/'code.vdb') not in ledger,'Not exact762 unique baseline')
    (output/'single-inputs.txt').write_text(ledger[0]+'\n'+str(p.RUN/'code.vdb')+'\n')
    single=bitmap.collect(output/'single-inputs.txt')
    before=json.loads((p.BASE/'combined-bits.json').read_bytes())
    q.need(len(before['tests'])==762 and before['tests']==ledger[1:],'762 bitmap/ledger identity differs')
    combined=bitmap.combine(before,single)
    delta=bitmap.delta(before,combined)
    (output/'combined-inputs.txt').write_text('\n'.join(ledger+[str(p.RUN/'code.vdb')])+'\n')
    q.save(output/'single-bits.json',single); q.save(output/'combined-bits.json',combined)
    q.save(output/'raw-delta.json',delta)
    for f,d in pins.items(): q.need(q.sha(f)==d,'Source changed during qualification: '+f)
    outputs={str(f):q.sha(f) for f in output.iterdir() if f.is_file()}
    admission=dict(status='INDEPENDENT763_ADMITTED_DEFINED_ARCHITECTURE_PASS',population=763,
        baseline=762,baseline_sha256=p.BASE_SHA,qualification_sha256=q.sha(output/'qualification.json'),
        input_pins=pins,output_pins=outputs,raw_gain=delta['metrics'],coverage_admitted=True,
        current_unified_reports_modified=False,DVE_launched=False,
        scoring='Raw line/cond/branch/FSM positions only; no DVE percentage claim; Toggle not calculated')
    q.save(output/'admission-manifest.json',admission)
    return admission


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    result=collect(args.output.absolute())
    print(json.dumps(dict(status=result['status'],seal=q.sha(args.output/'admission-manifest.json'),
                          raw_gain=result['raw_gain'])))
