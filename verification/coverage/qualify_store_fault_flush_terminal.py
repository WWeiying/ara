"""Terminal-only complete fault/recovery qualification; no VCS, raw gain or admission."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import struct

import run_store_fault_flush_simulation as runner
import collect_opivx_vsbc_strict as common
from ara_verify import vector_commit as vc
from ara_verify.contract import check_contract_log, parse_contract_summary

p, life, require = runner.p, runner.life, runner.require
STATUS = 'STORE_FAULT_FLUSH_OFFLINE_PLAN_NOT_EXECUTED'


def elf_instruction(blob, pc, width):
    require(width in (2,4) and blob[:6] == b'\x7fELF\x02\x01', 'ELF64 LE instruction required')
    header = struct.unpack_from('<HHIQQQIHHHHHH', blob, 16)
    require(header[:3] == (2,243,1) and header[10] == 64 and
            header[5]+header[11]*64 <= len(blob), 'ELF section table differs')
    owners = []
    for i in range(header[11]):
        section = struct.unpack_from('<IIQQQQIIQQ', blob, header[5]+i*64)
        if section[1] == 1 and section[2] & 4 and section[3] <= pc and pc+width <= section[3]+section[5]:
            offset = section[4]+pc-section[3]
            require(offset+width <= len(blob), 'Truncated executable bytes')
            owners.append(int.from_bytes(blob[offset:offset+width], 'little'))
    require(len(owners) == 1, 'Unique executable instruction owner required')
    return owners[0]


def terminal(state, actual, started, prepared):
    directory = Path(prepared['preflight']).parent
    require(state.get('status') == 'SIMULATION_EXITED_NOT_ADMITTED' and
        type(state.get('returncode')) is int and state['returncode'] == 0 and
        state.get('case') == p.NAME and state.get('timeout') is False and
        state.get('coverage_admitted') is False and state.get('admission_performed') is False and
        state.get('terminal_oracle_verified') is False, 'HOLD: unsuccessful/missing OS receipt')
    require(actual == prepared and started['command'] == prepared['command'] and
        started['input_elf'] == str(directory / 'input.elf') and
        started['elf_sha256'] == prepared['elf_sha256'] and
        started['image'] == str(life.IMAGE) and started['image_sha256'] == prepared['image_sha256'] and
        type(started['pid']) is int and started['pid'] > 0 and
        started['pid'] == started['process_group'] == state['pid'] and
        started['budget_s'] == 600 and started['foreground_lifetime'] is True and
        started['coverage_admitted'] is False, 'Actual startup/pins differ')
    require(type(state.get('wall_seconds')) in (int, float) and state['wall_seconds'] >= 0,
            'Missing actual wall receipt')


def lifecycle(rows, vectors, symbols, fault_word, recovery_word):
    starts, pending, live, intervals = {}, {}, {}, defaultdict(list)
    req, resp, rejected, ba, bd = Counter(), Counter(), [], Counter(), Counter()
    previous = -1
    for r in rows:
        event, cycle, seq, tid = r['event'], int(r['cycle']), int(r['order']), int(r['trans_id'])
        require(cycle >= previous, 'Commit time reversed'); previous = cycle
        if event == 'arch_start':
            require(seq >= 0 and seq not in starts and tid not in pending, 'Duplicate architecture/transaction')
            starts[seq], pending[tid] = r, [seq, False]
        elif event == 'cvx_req':
            require(tid in pending and not pending[tid][1], 'Unowned/duplicate request')
            s = pending[tid][0]
            require(r['insn'] == starts[s]['insn'], 'Request instruction differs')
            pending[tid][1] = True; req[s] += 1
        elif event == 'cvx_resp':
            require(tid in pending and pending[tid][1] and seq == -1 and
                    int(r['pc'], 16) == int(r['insn'], 16) == 0 and int(r['trap']) in (0, 1),
                    'Unknown response/placeholder')
            s = pending.pop(tid)[0]; resp[s] += 1
            if int(r['trap']): rejected.append(s)
        elif event in ('uop_alloc', 'uop_done'):
            vid = int(r['port'])
            require(seq in starts and 0 <= vid < 8 and tid == int(starts[seq]['trans_id']) and
                    r['insn'] == starts[seq]['insn'] and cycle >= int(starts[seq]['cycle']), 'Backend identity differs')
            if event == 'uop_alloc':
                require(vid not in live, 'Live SID reused')
                item = dict(seq=seq, start=cycle, end=None)
                live[vid] = item; intervals[vid].append(item); ba[seq, vid, cycle] += 1
            else:
                require(vid in live and live[vid]['seq'] == seq and cycle >= live[vid]['start'], 'Unowned completion')
                live.pop(vid)['end'] = cycle; bd[seq, vid, cycle] += 1
        else:
            require(event == 'retire' and (not int(r['trap']) or
                    (int(r['pc'], 16) == symbols['sff_fault'] and int(r['insn'], 16) == fault_word)),
                    'Unexpected event/trap')
    require(not pending and req == resp == Counter(starts.keys()) and not live and
            Counter((s,v) for s,v,c in ba.elements()) == Counter((s,v) for s,v,c in bd.elements()),
            'CVX/backend conservation differs')
    fault = [s for s,r in starts.items() if int(r['insn'],16) == fault_word]
    require(len(fault) == 1 and rejected == fault and any(s == fault[0] for s,v,c in ba),
            'Exact backend fault request missing')
    va, vd, metadata, previous = Counter(), Counter(), {}, -1
    for r in vectors:
        cycle, seq, vid, event = int(r['cycle']), int(r['arch_seq']), int(r['vid']), r['event']
        require(cycle >= previous and (int(r['nr_lanes']),int(r['vlen_bits'])) == (4,1024), 'Native time/geometry differs')
        previous = cycle
        if event == 'config': continue
        require(seq in starts and r['insn'] == starts[seq]['insn'] and event in ('alloc','done','write'),
                'Native opcode/owner differs')
        if event == 'alloc':
            key = seq, vid, cycle
            require(key not in metadata, 'Duplicate native allocation')
            metadata[key] = r; va[key] += 1
        else:
            eligible = [a for a in intervals[vid] if a['start'] < cycle]
            if not eligible: eligible = [a for a in intervals[vid] if a['start'] == cycle]
            require(eligible, 'Missing SID history')
            owner = eligible[-1]; key = seq, vid, owner['start']
            require(owner['seq'] == seq and owner['start'] <= cycle <= owner['end'] and key in metadata and
                    all(r[k] == metadata[key][k] for k in ('insn','use_vd','vd','eew','vl','vstart')),
                    'Native SID/metadata drift')
            if event == 'done': vd[seq,vid,cycle] += 1
            else: require(int(r['use_vd']) == 1 and seq != fault[0] and 0 <= int(r['lane']) < 4,
                          'Faulting store/invalid VRF writer')
    require(va == ba and vd == bd, 'Native/commit event identity differs')
    recovered = [r for r in rows if r['event'] == 'retire' and int(r['pc'],16) == symbols['sff_recovery']]
    require(len(recovered) == 1 and int(recovered[0]['insn'],16) == recovery_word and not int(recovered[0]['trap']),
            'Missing exact recovery retirement')
    recovery = [s for s,r in starts.items() if int(r['insn'],16) == recovery_word]
    # Dumps may use the same instruction word, so identify the recovery via architecture retirement mapping later.
    require(recovery and any(s > fault[0] for s in recovery), 'Recovery request missing')
    return dict(requests=sum(req.values()), responses=sum(resp.values()), exceptions=1,
                fault_arch_seq=fault[0], backend_uops=sum(ba.values()), current_SID_owner_checked=True)


def observed(rows, symbols, directory):
    footprints = [(symbols[n], symbols[n]+160) for n in ('sff_a','sff_b','sff_dest','sff_dump_a','sff_dump_b')]
    footprints += [(symbols[n], symbols[n]+size) for n,size in
                   [('sff_index',16),('sff_trap',80),('sff_cfg',64),('sff_env',48),('sff_count',8),('sff_marker',8)]]
    retired = [r for r in rows if r['event'] == 'retire']
    require(retired and [int(r['order']) for r in retired] == list(range(len(retired))), 'Incomplete retirement order')
    memory, reads, terminals = {}, set(), []
    elf = (directory / 'input.elf').read_bytes()
    for r in retired:
        pc, insn = int(r['pc'],16), int(r['insn'],16)
        width = 2 if insn & 3 != 3 else 4
        require(elf_instruction(elf, pc, width) == insn and pc != symbols['trap_fail'],
                'Retirement opcode outside sealed ELF/fatal path')
        if int(r['trap']):
            require(pc == symbols['sff_fault'] and int(r['mem_wmask'],16) == 0, 'Unexpected trap/write')
            continue
        access = common.scalar_memory(insn)
        rm, wm, addr = int(r['mem_rmask'],16), int(r['mem_wmask'],16), int(r['mem_addr'],16)
        if access is None:
            require(not rm and not wm, 'Unknown scalar memory effect'); continue
        kind, size = access; mask = ((1 << size)-1) << (addr & 7)
        require(addr % size == 0 and rm == (mask if kind == 'read' else 0) and
                wm == (mask if kind == 'write' else 0), 'Memory mask/alignment differs')
        if kind == 'write':
            value = int(r['mem_wdata'],16) & ((1 << (8*size))-1)
            if addr == symbols['tohost']: terminals.append(r)
        elif any(a <= addr and addr+size <= b for a,b in footprints):
            require(int(r['rd']) != 0, 'Unobservable oracle readback')
            value = int(r['rd_wdata'],16) & ((1 << (8*size))-1); reads.update(range(addr,addr+size))
        else: continue
        memory.update({addr+i:b for i,b in enumerate(value.to_bytes(size,'little'))})
    require(terminals == [retired[-1]], 'Missing/extra/nonfinal tohost')
    require(reads == {x for a,b in footprints for x in range(a,b)}, 'Incomplete source/destination/trap readback')
    def read(n, i=0, size=8):
        a = symbols[n]+i*size
        require(all(a+j in memory for j in range(size)), 'Missing oracle bytes: '+n)
        return int.from_bytes(bytes(memory[a+j] for j in range(size)), 'little')
    require(read('g75_result',size=4) == 134 and read('g75_result',1,4) == read('num_failed',size=4) == 0 and
            read('tohost') == read('sff_count') == read('sff_marker') == 1, 'Software signature differs')
    for b,n in enumerate(('sff_a','sff_b','sff_dest','sff_dump_a','sff_dump_b')):
        require([read(n,i) for i in range(20)] == [p.expected(b,i) for i in range(20)], 'Buffer/guard differs: '+n)
    require([read('sff_index',i,2) for i in range(8)] == list(p.OFFSETS), 'Index footprint differs')
    trap = [read('sff_trap',i) for i in range(10)]; trap[7] &= 0x21800
    require(trap == [1,7,p.BAD,symbols['sff_fault'],0,8,24,0x1800,0,0], 'Exact trap/privilege ledger differs')
    require([read('sff_cfg',i) for i in range(8)] == [8,24,0,128]*2 and
            [read('sff_env',i) for i in range(6)] == [0]*6, 'Vector/bare M environment differs')
    return dict(checks=134, failed_checks=0, source_destination_dump_words=100,
                explicit_readback_bytes=len(reads), cause=7,tval=p.BAD,vstart=0,recovery_words=8)


def scalar_exact(result, counts, symbols):
    fixed = dict(status='TERMINAL_TOHOST_MATCH', entry='0x0000000080000000',
        rvfi_store_data_layout='unshifted', skipped_unobservable_register_values=0,
        stopped_at_unobservable=None, mismatch=None, terminal_ecall=None)
    fixed.update({k:v for k,v in counts.items() if k != 'matched_instructions'})
    require(all(result.get(k) == v for k,v in fixed.items()), 'Complete scalar comparison differs')
    faults = result['aligned_vector_faults']
    require(len(faults) == 1 and int(faults[0]['pc'],16) == symbols['sff_fault'] and
            faults[0]['fault_handler_returned'] is True and faults[0]['matched_fault_csrs'] ==
            {'0x341':symbols['sff_fault'],'0x342':7,'0x343':p.BAD}, 'Fault CSR alignment differs')
    require(result['matched_instructions'] == counts['matched_instructions']-1 and
            result['ara_committed_instructions'] == result['matched_instructions'] and
            result['ara_trap_events'] in (0,1) and result['ara_retired_instructions'] ==
            result['ara_committed_instructions']+result['ara_trap_events'], 'Incomplete scalar retirement count')


def verify_prepared(run, prepared):
    require(run.parent == life.OUT and run.resolve() == run and
            prepared['output'] == str(run), 'Prepared output identity differs')
    directory = Path(prepared['preflight']).parent
    pre = runner.verify_preflight(directory, prepared['preflight_seal'])
    image = life.read_bound(runner.preflight.guarded.PLAN, runner.preflight.guarded.PLAN_SHA)
    require(len(image['image']) == 66 and image['simv'] == str(life.IMAGE) and
            image['image'][str(life.IMAGE)] == runner.preflight.guarded.IMAGE_SHA,
            'Prepared fixed-image authority differs')
    expected = dict(case=p.NAME, command=runner.command(run, directory), timeout_s=600,
        old_image_files_checked=66, image_sha256=runner.preflight.guarded.IMAGE_SHA,
        elf_sha256=pre['input_elf_sha256'], software_checks=134,
        static_provenance_population=731, raw_gain_requires_latest_formal_baseline_at_least=732,
        foreground_lifetime=True, automatic_retry=False, coverage_admitted=False,
        admission_performed=False, native_internal_timing_observed=False,
        systemd_policy=dict(RuntimeMaxSec=660, TimeoutStopSec=10, KillMode='control-group'),
        parent_review_required=True)
    require(all(prepared.get(k) == v for k, v in expected.items()),
            'Prepared execution contract differs')
    required = life.merge_pins(pre['pins'], image['image'])
    required = life.merge_pins(required, {
        str(directory/'preflight-manifest.json'): prepared['preflight_seal'],
        str(runner.preflight.guarded.PLAN): runner.preflight.guarded.PLAN_SHA,
        str(Path(runner.frozen.__file__).resolve()): runner.LIFECYCLE_SHA})
    require(all(prepared['pins'].get(k) == v for k, v in required.items()),
            'Prepared input obligations differ')
    life.check(prepared['pins'])


def prepare(run, runseal, output):
    record = run.with_name(run.name+'.prepared.json')
    prepared = life.read_bound(record, runseal)
    directory = Path(prepared['preflight']).parent
    preseal = prepared['preflight_seal']
    verify_prepared(run, prepared)
    require(output.parent == life.OUT and output.resolve() == output and not output.exists(), 'Fresh plan required')
    deps = [Path(__file__).resolve(), Path(__file__).with_name('test_qualify_store_fault_flush_terminal.py'),
            Path(common.__file__).resolve(), *sorted((life.ROOT/'verification/ara_verify').glob('*.py'))]
    pins = life.merge_pins(prepared['pins'], {str(x):life.digest(x) for x in deps})
    sourcebook = p.BUILD/'build-source-pins.json'
    sources = life.read_bound(sourcebook,'6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b')
    monitor = life.ROOT/'hardware/tb/ara_commit_monitor.sv'
    pins = life.merge_pins(pins,{str(record):runseal,str(monitor):sources[str(monitor)]})
    life.check(pins); output.mkdir()
    life.save(output/'plan.json', dict(status=STATUS,run=str(run),prepared=str(record),prepared_seal=runseal,
        preflight=str(directory/'preflight-manifest.json'),preflight_seal=preseal,
        pins=pins,coverage_admitted=False,raw_gain_requires_latest_formal_baseline_at_least=732,
        expected_checks=134,expected_cause=7,expected_vstart=0,native_internal_timing_claimed=False))
    print(json.dumps(dict(plan=str(output/'plan.json'),seal=life.digest(output/'plan.json'),vcs_started=False)))


def collect(planpath, seal, out):
    plan = life.read_bound(planpath,seal); require(plan['status']==STATUS,'Plan identity differs'); life.check(plan['pins'])
    run = Path(plan['run']); require((run/'simulation-status.json').is_file(),'No terminal receipt: do not read active trace')
    require(out.parent == life.OUT and out.resolve()==out and not out.exists(),'Fresh collection required')
    pins = life.merge_pins(plan['pins'],{str(planpath):seal})
    def read(n):
        path = run/n; require(path.resolve()==path and not path.is_symlink(),'Aliased evidence')
        raw = path.read_bytes(); h=hashlib.sha256(raw).hexdigest()
        require(life.digest(path)==h,'Evidence changed while reading'); pins[str(path)]=h; return raw
    prepared=life.read_bound(Path(plan['prepared']),plan['prepared_seal'])
    require(prepared['output'] == str(run) and prepared['preflight'] == plan['preflight'] and
            prepared['preflight_seal'] == plan['preflight_seal'], 'Explicit plan/preflight binding differs')
    directory = Path(plan['preflight']).parent
    terminal(json.loads(read('simulation-status.json')),json.loads(read('manifest.json')),json.loads(read('started.json')),prepared)
    out.mkdir()
    try:
        pre=runner.verify_preflight(directory,plan['preflight_seal']); symbols=pre['symbols']
        rows=common.read_csv(read('commit_trace.csv'),common.COMMIT_FIELDS)
        vectors=common.read_csv(read('vector_trace.csv'),common.VECTOR_FIELDS)
        proof=json.loads((directory/'linked-proof.json').read_bytes())
        control=lifecycle(rows,vectors,symbols,proof['fault_opcode'],proof['recovery_opcode'])
        signature=observed(rows,symbols,directory)
        console=read('console.log').decode(); log=read('run.vcs.log').decode()
        for text in (console,log):
            require(not re.search(r'Fatal:|Error:|Fatal-\[|Error-\[|\[ARA_CONTRACT_ERROR\]|Core Test \*\*\* FAILED',text),'Simulator/protocol failure')
            for line in text.splitlines():
                if re.search(r'\bUVM_(ERROR|FATAL)\b',line):
                    require(re.fullmatch(r'\s*UVM_(ERROR|FATAL)\s*:\s*0+\s*',line),'HOLD: unexpected UVM error')
        require(log.count('Core Test *** SUCCESS ***')==1 and not check_contract_log(run/'run.vcs.log'),'Incomplete/error terminal log')
        summaries=[parse_contract_summary(l.strip()) for l in console.splitlines() if '[ARA_CONTRACT]' in l]
        require(len(summaries)==1 and summaries[0] is not None,'Missing/extra contract')
        counts=summaries[0]
        require(counts['requests']==counts['responses']==control['requests'] and counts['exceptions']==1 and
                all(counts[k]==0 for k in ('protocol_errors','outstanding','req_stalled','resp_stalled')),'Contract differs')
        tracer=read('trace_hart_0.log').decode(); read('trace_hart_0_commit.log')
        exceptions=re.findall(r'^Exception @\s+\d+, PC: ([0-9a-fA-F]+),.*$',tracer,re.M)
        require(len(exceptions)==1 and int(exceptions[0],16)==symbols['sff_fault'],'Exact tracer exception differs')
        reference=p.shared.parse_spike_commits(directory/'spike.trace')
        scalar=common.spike_trace.compare_commit_prefix(directory/'spike.trace',run/'commit_trace.csv',
            0x80000000,terminal_tohost_address=0x80001000,rtl_exception_log=run/'trace_hart_0.log',rvfi_store_data_layout='unshifted')
        life.save(out/'scalar-comparison.json',scalar); scalar_exact(scalar,common.reference_counts(reference,symbols),symbols)
        vector=common.compare_vector_commits(directory/'spike.trace',run/'commit_trace.csv',run/'vector_trace.csv',0x80000000)
        life.save(out/'vector-comparison.json',vector)
        expected=[c for c in reference if c.vector_writes]
        require(vector['status']=='PASS' and vector['compared_instructions']==len(expected) and
            vector['compared_bytes']==272 and vector['trapped_requests']==[control['fault_arch_seq']] and
            all(vector[k]==0 for k in ('skipped_unknown_bytes','non_bit_exact_instructions','unobservable_instructions')) and
            not vector['first_mismatch'] and not vector['incomplete_requests'] and not vector['unretired_requests'],
            'Full vector comparison differs')
        lanes,vlen,activities=vc._parse_vector_trace(run/'vector_trace.csv')
        starts,retires,rejected=vc._parse_architecture_mapping(run/'commit_trace.csv')
        mapping=vc._map_spike_commits(vc._map_architecture_retires(starts,retires,rejected),reference)
        require((lanes,vlen)==(4,1024) and rejected=={control['fault_arch_seq']},'Native fault/geometry differs')
        wanted={s:reference[i] for s,i in mapping.items() if reference[i].vector_writes}
        require({s for s,a in activities.items() if a.writes}==set(wanted),'Extra/missing native writer')
        for s,c in wanted.items():
            writes=activities[s].writes; seen=set()
            for w in writes:
                require(w.source==4 and w.be & ~w.known_be==0,'Unknown/non-VLDU writer')
                for b in range(8):
                    if w.be & (1<<b):
                        key=w.addr,w.lane,b; require(key not in seen,'Duplicate accepted native byte'); seen.add(key)
            actual=vc._architectural_bytes(writes,4,1024)
            require({k:v for k,(v,_) in actual.items()}==
                {(reg,b):(value>>(8*b))&255 for reg,value in c.vector_writes.items()
                 for b in range(16 if reg==4 else 128)},'Complete native seed bytes differ')
        life.check(pins)
        life.save(out/'observed-memory.json',signature); life.save(out/'lifecycle.json',control)
        outputs={str(x):life.digest(x) for x in out.iterdir() if x.is_file()}
        life.save(out/'qualification.json',dict(status='STORE_FAULT_FLUSH_FULL_RETIREMENT_MEMORY_NATIVE_PASS_NOT_ADMITTED',
            pins=life.merge_pins(pins,outputs),checks=134,UVM_errors=0,OS_returncode=0,
            terminal_source='FOREGROUND_RUNNER_OS_RETURN_RECEIPT',static_provenance_population=731,
            raw_gain_requires_latest_formal_baseline_at_least=732,coverage_admitted=False,
            whole_ISA_qualified=False,native_B_error_plus_addr_fault_timing_measured=False,
            target_hit_verified=False,raw_gain_not_collected=True))
        print(json.dumps(dict(seal=life.digest(out/'qualification.json'),coverage_admitted=False)))
    except Exception as e:
        life.save(out/'failure.json',dict(status='QUALIFICATION_HOLD_NOT_ADMITTED',reason=str(e),pins=pins))
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','verify','collect'))
    parser.add_argument('--run',type=Path); parser.add_argument('--run-seal')
    parser.add_argument('--plan',type=Path); parser.add_argument('--seal'); parser.add_argument('--output',type=Path)
    a=parser.parse_args()
    if a.mode=='prepare':
        require(a.run is not None and a.run_seal and a.output is not None,'Run review and output required')
        prepare(a.run.absolute(),a.run_seal,a.output.absolute())
    else:
        require(a.plan is not None and a.seal,'Plan/seal required')
        if a.mode=='collect':
            require(a.output is not None,'Fresh output required'); collect(a.plan.absolute(),a.seal,a.output.absolute())
        else:
            plan=life.read_bound(a.plan,a.seal); require(plan['status']==STATUS,'Wrong plan'); life.check(plan['pins'])
            print('VERIFY_PASS NO_DUT_READ NO_VCS')


if __name__=='__main__': main()
