"""Offline native owner/recovery and preedge fault evidence; no population admission."""
import argparse
import csv
import json
from io import BytesIO
from pathlib import Path
import re
import struct
import subprocess
from types import FunctionType
from collections import deque

from elftools.elf.elffile import ELFFile
from ara_verify.vector_commit import _parse_vector_trace, _architectural_bytes
import audit_gap115_axi_v2 as wave
import run_gap71_canonical_qbs_positive779 as runner

life, require = runner.life, runner.require
SCOPE = runner.probe_contract()['scope']
CONVERTER = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/linux64/bin/vpd2vcd.exe')
CONVERTER_SHA = '195fae31e4cbacabcbbd97bfd61c98a333f68ff2fd013002ab322e5108f97002'
FAULT = 0x1555402080


def terminal_gate(terminal, started, manifest, out):
    require(type(terminal.get('returncode')) is int and terminal['returncode'] == 0
        and terminal.get('timeout') is False
        and terminal.get('status') == 'SIMULATION_EXITED_NOT_ADMITTED'
        and terminal.get('coverage_admitted') is False, 'Actual successful terminal required')
    require(type(started.get('pid')) is int and started['pid'] > 0
        and terminal['pid'] == started['pid'] and started['budget_s'] == 600
        and started['command'] == manifest['command'] == runner.command(out)
        and started['image_sha256'] == runner.inherited.IMAGE_SHA
        and started['elf_sha256'] == runner.ELF_SHA, 'Exact process/image/ELF contract')


def markers(text):
    lines = text.splitlines()
    expected = ['CANONICAL_QBS_OBJECT ' + SCOPE + '.' + n for n in runner.PROBE_NAMES]
    require([l for l in lines if l.startswith('CANONICAL_QBS_OBJECT ')] == expected
        and lines.count('CANONICAL_QBS_PROBE_READY') == 1
        and not any(l.startswith('CANONICAL_QBS_PROBE_REJECT') for l in lines),
        'Exact executed probe markers required')


def recovery_words(blob, pc):
    elf = ELFFile(BytesIO(blob))
    segments = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD'
        and s['p_vaddr'] <= pc and pc + 12 <= s['p_vaddr'] + s['p_filesz']]
    require(len(segments) == 1, 'Exact recovery code segment')
    segment = segments[0]; offset = pc - segment['p_vaddr']
    words = struct.unpack('<3I', segment.data()[offset:offset+12])
    require(words[0] & ~(31<<15) == 0x02007507
        and words[1] == ((1<<25)|(10<<20)|(10<<15)|(11<<7)|0x57)
        and words[2] & ~(31<<15) == 0x020075a7, 'Exact recovery vle64/vadd/vse64 sites')
    return words


def recovery_gate(rows, activities, info, blob):
    pc = info['symbols']['canon_recovery_site']; words = recovery_words(blob, pc)
    sites = {pc + i*4: w for i,w in enumerate(words)}
    starts = [r for r in rows if r['event'] == 'arch_start' and int(r['pc'],16) in sites]
    require([int(r['pc'],16) for r in starts] == list(sites)
        and [int(r['insn'],16) for r in starts] == list(words), 'Unique ordered native recovery requests')
    seqs = [int(r['order']) for r in starts]
    require(len(seqs) == len(set(seqs)) == 3, 'Distinct recovery identities')
    retired = [r for r in rows if r['event'] == 'retire' and int(r['pc'],16) in sites]
    require([int(r['pc'],16) for r in retired] == list(sites)
        and [int(r['insn'],16) for r in retired] == list(words)
        and all(int(r['trap']) == 0 for r in retired), 'Recovery retirement/fault differs')
    for i,seq in enumerate(seqs):
        require(seq in activities, 'Missing recovery vector activity')
        a = activities[seq]
        require(a.instruction == words[i] and a.allocations == a.completions == 1,
            'Recovery vector metadata/lifecycle differs')
        if i != 2:
            require((a.vl,a.vstart,a.eew) == (16,0,3), 'Recovery writer configuration')
        require(all(w.eew == 3 and 0 <= w.lane < 4 and 0 < w.be <= 255
            and w.be & ~w.known_be == 0 for w in a.writes), 'Recovery write byte/EEW/lane validity')
        if i == 2: require(not a.writes, 'Recovery store must not write VRF')
        values = {k: v for k,(v,_) in _architectural_bytes(a.writes,4,1024).items()}
        want = {} if i == 2 else {(10+i,j): v for j,v in enumerate(struct.pack('<16Q',
            *[(runner.p.recovery_word(k)*(i+1)) & ((1<<64)-1) for k in range(16)]))}
        require(values == want, 'Full recovery defined bytes differ')
    return set(seqs), dict(status='PASS', instruction_sites=[hex(x) for x in sites],
        source_bytes=128, destination_bytes=128, store_instruction_writes_VRF=False)


def recovery_lifetimes(vector, seqs):
    groups = {}
    with vector.open(newline='') as stream:
        for row in csv.DictReader(stream):
            seq = int(row['arch_seq'])
            if row['event'] == 'config' or seq not in seqs: continue
            cycle = int(row['cycle']); event = row['event']
            if event == 'alloc':
                require(seq not in groups, 'Duplicate recovery allocation')
                require(tuple(int(row[k]) for k in ('eew','vl','vstart')) == (3,16,0),
                    'Recovery exact alloc state')
                groups[seq] = dict(start=cycle,done=None,vid=row['vid'])
            else:
                require(seq in groups and row['vid'] == groups[seq]['vid'], 'Unowned recovery event')
                group = groups[seq]
                require(cycle >= group['start'], 'Recovery event precedes allocation')
                if event == 'done':
                    require(group['done'] is None, 'Duplicate recovery completion')
                    require(tuple(int(row[k]) for k in ('eew','vl','vstart')) == (3,16,0),
                        'Recovery exact done state')
                    group['done'] = cycle
                else:
                    require(event == 'write' and int(row['eew']) == 3
                        and (group['done'] is None or cycle == group['done']),
                        'Recovery write outside lifetime')
    require(set(groups) == seqs and all(g['done'] is not None for g in groups.values()),
        'Missing recovery lifetime')


def native_architecture(commit, vector, info, blob, output):
    with commit.open(newline='') as stream: rows = list(csv.DictReader(stream))
    retires = [r for r in rows if r['event'] == 'retire']
    require(retires and [int(r['order']) for r in retires] == list(range(len(retires))),
        'Complete contiguous retirement stream')
    last = retires[-1]
    require(int(last['mem_addr'],16) == 0x80001000 and int(last['mem_wmask'],16) == 255
        and int(last['mem_wdata'],16) == 1 and not int(last['trap']), 'Exact terminal tohost store')
    lanes, vlen, activities = _parse_vector_trace(vector)
    require((lanes,vlen) == (4,1024), 'Frozen VRF geometry')
    for activity in activities.values():
        require(all(w.be & ~w.known_be == 0 for w in activity.writes), 'Unknown enabled vector byte')
    seqs, recovery = recovery_gate(rows, activities, info, blob)
    recovery_lifetimes(vector, seqs)
    starts = [(int(r['order']),int(r['insn'],16)) for r in rows
        if r['event'] == 'arch_start' and int(r['insn'],16)&127 == 0x5b]
    runner.p.audit.custom_write_lifetimes(vector, starts)
    # Only three independently verified recovery identities are projected away.
    # Every custom event, seed, CSR and scalar read remains in the inherited gate.
    projected = output / 'owner-vector-projection.csv'
    with vector.open(newline='') as stream, projected.open('x',newline='') as target:
        reader = csv.DictReader(stream); writer = csv.DictWriter(target,fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            if row['event'] == 'config' or int(row['arch_seq']) not in seqs: writer.writerow(row)
    oracle = runner.p.oracle(runner.p.WINDOWS['positive'])
    owner = oracle['runtime_traces'](commit, projected, 'gap71_qbs_fault', info)
    return dict(owner=owner, recovery=recovery, retirement_count=len(retires),
        scalar_policy='Inherited native CSR/PTE/data/guard/fullVRF readback and owner gates; no software/native instruction-stream equality claim',
        last_cycle=max(int(r['cycle']) for r in rows))


def cycle_gate(samples, last_cycle=0):
    outstanding = deque(); held = None; faults = []; acknowledgements = []; ar = rlast = ticks = 0
    retry = False; terminal_idle = False
    for time, s in samples:
        def v(name):
            value = s.get(name)
            require(type(value) is int and value >= 0, 'Unknown/missing active sample: '+name)
            return value
        if not v('rst_ni'):
            require(not outstanding and not faults and ar == 0, 'Unexpected active reset')
            ticks = 0
            continue
        ticks += 1
        count = v('burst_fifo_count_q'); pending = v('fault_pending_q'); stalled = v('ar_stalled_q')
        av, ready, rv, rr = [v(n) for n in ('axi_ar_valid_o','axi_ar_ready_i','axi_r_valid_i','axi_r_ready_o')]
        require(count == len(outstanding), 'AR/RLAST burst FIFO conservation')
        fv = v('fault_valid_o')
        require(fv == int(bool(pending and count == 0 and not stalled)), 'Exact faultvalid preedge gate')
        require(v('response_fault_event') == 0 and v('response_drain_q') == 0,
            'Unexpected AXI response fault/drain in MMU-only fixture')
        addr = v('axi_ar_o.addr') if av else None
        if held is not None: require(av and addr == held, 'AR changed while held')
        if pending and av: require(stalled and held is not None, 'New AR after fault pending')
        held = addr if av and not ready else None
        if v('planner_fault_event'):
            require(v('en_ld_st_translation_i') == 1 and v('plan_state_q') == 2
                and v('mmu_req_o') == 1 and v('mmu_vaddr_o') == FAULT
                and v('mmu_exception_valid_i') == 1
                and v('mmu_exception_i.cause') == 13 and v('mmu_exception_i.tval') == FAULT
                and v('planner_fault_kind') == 2 and v('planner_fault_vaddr') == FAULT
                and v('physical_check_valid_o') == 0 and not av,
                'Exact target MMU fault must suppress PMA and AR')
            for name in sorted(k for k in s if k.startswith('mmu_exception_i.')):
                require(v(name) == v(name.replace('mmu_exception_i.','planner_fault_mmu_exception.')),
                    'Planner exception projection differs')
            faults.append(dict(time=time, outstanding=count))
        if fv:
            require(v('fault_kind_o') == 2 and v('fault_vaddr_o') == FAULT
                and v('fault_mmu_exception_o.cause') == 13
                and v('fault_mmu_exception_o.tval') == FAULT and not av,
                'Fault output identity/drained AR differs')
            if v('fault_ready_i'): acknowledgements.append(time)
        if v('en_ld_st_translation_i') and v('mmu_req_o') and v('mmu_exception_valid_i'):
            require(not v('physical_check_valid_o'), 'MMU exception leaked to PMA')
        if v('mmu_req_o') and v('mmu_vaddr_o') == FAULT and v('mmu_valid_i') and not v('mmu_exception_valid_i'):
            require(acknowledgements and v('physical_check_valid_o') and v('physical_range_allowed_i'),
                'Target retry did not translate before permitted PMA')
            retry = True
        if av and ready:
            outstanding.append(addr); ar += 1
        if rv and rr:
            require(outstanding and v('axi_r_i.resp') in (0,1), 'Orphan/error accepted R')
            if v('axi_r_i.last'): outstanding.popleft(); rlast += 1
        terminal_idle = not outstanding and not pending and not av and v('plan_state_q') == 0
    require(len(faults) == len(acknowledgements) == 1 and faults[0]['time'] < acknowledgements[0]
        and retry and terminal_idle and ar == rlast > 0 and ticks > last_cycle,
        'Missing fault/drain/repair-retry/end-of-trace evidence')
    return dict(status='PASS', fault=faults[0], acknowledgement=acknowledgements[0],
        target_retry_translated=True, accepted_AR=ar, accepted_RLAST=rlast, sampled_edges=ticks,
        per_beat_protocol_certified=False, limitation='AR.len not captured; no per-burst beat-length claim')


def cycle_wave(path, last_cycle):
    parse = FunctionType(wave.vcd.__code__,dict(wave.vcd.__globals__,ROOT=SCOPE,WIDTHS={'clk_i':1,'rst_ni':1}))
    iterator = iter(parse(path)); _, decl = next(iterator)
    names = {name[len(SCOPE)+1:]: value for name,value in decl.items() if name.startswith(SCOPE+'.')}
    for name in runner.PROBE_NAMES:
        require(name in names or any(k.startswith(name+'.') for k in names), 'Missing exact waveform object: '+name)
    for field in ('mmu_exception_i','planner_fault_mmu_exception','fault_mmu_exception_o'):
        require(names.get(field+'.cause',{}).get('width') == 64
            and names.get(field+'.tval',{}).get('width') == 64, 'Frozen exception member shape')
    def frames():
        clk = names['clk_i']['code']
        for time,before,after in iterator:
            if before.get(clk) != '0' or after.get(clk) != '1': continue
            state = {}
            for name, item in names.items():
                bits = before.get(item['code'],'x')
                state[name] = int(bits,2) if set(bits) <= set('01') else None
            yield time,state
    return cycle_gate(frames(),last_cycle)


def collect(run, seal, output):
    require(output.parent == life.OUT and not output.exists(), 'Fresh standalone collector output')
    prepared = run.with_name(run.name+'.prepared.json')
    manifest = life.read_bound(prepared,seal)
    require(life.read_bound(run/'manifest.json',seal) == manifest and manifest['output'] == str(run),
        'Prepared/executed bytes differ')
    life.check(manifest['pins'])
    require(manifest['timeout_s'] == 600 and manifest['baseline'] == 779
        and manifest['preflight_seal'] == runner.PRE_SHA
        and manifest['probes'] == runner.probe_contract(), 'Exact reviewed native probe contract')
    terminal_gate(json.loads((run/'simulation-status.json').read_text()),
        json.loads((run/'started.json').read_text()),manifest,run)
    wavefile = run/'qbs-canonical-focused.vpd'
    require(wavefile.is_file() and 0 < wavefile.stat().st_size <= 64*1024*1024, 'Complete focused VPD <=64MiB required')
    markers((run/'console.log').read_text())
    artifacts = [run/n for n in ('manifest.json','simulation-status.json','started.json','console.log',
        'run.vcs.log','commit_trace.csv','vector_trace.csv','qbs-canonical-focused.vpd')]
    data = run/'code.vdb/snps/coverage/db/testdata'
    require(data.is_dir() and len(list(data.glob('*/tgl.verilog.data.xml'))) == 1,
        'Actual complete VDB testdata required')
    artifacts += [p for p in (run/'code.vdb').rglob('*') if p.is_file()]
    require(all(p.is_file() and not p.is_symlink() for p in artifacts), 'Missing/aliased native artifacts')
    pins = life.merge_pins(manifest['pins'],{str(p):life.digest(p) for p in artifacts})
    require(life.digest(CONVERTER) == CONVERTER_SHA, 'Pinned VPD converter')
    pins = life.merge_pins(pins,{str(prepared):seal,str(CONVERTER):CONVERTER_SHA})
    output.mkdir()
    try:
        vcd = output/'focused.vcd'
        with (output/'conversion.log').open('x') as log:
            subprocess.run([str(CONVERTER),'+splitpacked',str(wavefile),str(vcd)],
                stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
        require(vcd.is_file() and vcd.stat().st_size <= 512*1024*1024,'Bounded converted evidence')
        pre = life.read_bound(runner.PRE,runner.PRE_SHA); info = pre['artifacts']['dut']['metadata']
        architecture = native_architecture(run/'commit_trace.csv',run/'vector_trace.csv',info,runner.ELF.read_bytes(),output)
        cycles = cycle_wave(vcd,architecture['last_cycle'])
        log = (run/'run.vcs.log').read_text()
        require(log.count('Core Test *** SUCCESS ***') == 1 and not re.search(r'(?m)^.*UVM_(?:ERROR|FATAL)(?!\s*:\s*0\s*$)',log), 'Runtime failure')
        oracle = runner.p.oracle(runner.p.WINDOWS['positive'])
        uart = oracle['validate_log'](log,'gap71_qbs_fault','custom-dut')
        perf = oracle['runtime_perf'](log,'gap71_qbs_fault')
        for name,value in [('architecture.json',architecture),('cycles.json',cycles),('uart.json',uart),('perf.json',perf)]:
            life.save(output/name,value)
        for name in ('collect_gap71_canonical_qbs_positive779.py','test_collect_gap71_canonical_qbs_positive779.py'):
            path = Path(__file__).with_name(name); pins[str(path)] = life.digest(path)
        pins[str(Path(wave.__file__).resolve())] = life.digest(Path(wave.__file__))
        life.check(pins)
        life.save(output/'receipt.json',dict(status='NATIVE_OWNER_RECOVERY_CYCLE_GATES_PASS_NOT_ADMITTED',
            input_pins=pins,output_pins={str(p):life.digest(p) for p in output.iterdir()},
            native_Spike_instruction_stream_comparison=False, per_beat_protocol_certified=False,
            independent_full_scalar_ISA_replay=False, measured_raw_gain=None,coverage_admitted=False))
    except Exception as error:
        life.save(output/'rejection.json',dict(reason=str(error),coverage_admitted=False)); raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True); parser.add_argument('--seal',required=True)
    parser.add_argument('--output',type=Path,required=True); args=parser.parse_args()
    collect(args.run.resolve(),args.seal,args.output.resolve())
