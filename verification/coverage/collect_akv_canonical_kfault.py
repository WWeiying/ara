"""Offline exact AKV owner/architecture/fault wave checks; never admission."""
import argparse
import csv
import json
import re
import subprocess
from collections import deque
from pathlib import Path
from types import FunctionType

import run_akv_canonical_kfault as runner
import collect_gap71_canonical_qbs_positive779 as prior

life, require, p = runner.life, runner.require, runner.p


def outputs(index):
    pages = p.pages(0x80040000, index, False); rows = []
    for j in range(4):
        row = [p.audit.seed(k) for k in range(512)]
        if j:
            stream = j-1
            off = 16 if stream == 0 else (p.ADDRESSES[index] & 4095)//8 if stream == 1 else 64
            row[128:144] = pages[5 if stream == 0 else 4][off:off+16]
        rows.append(row)
    return rows


def owner_oracle(index):
    ns = dict(vars(p.audit))
    for name, value in vars(p.audit).items():
        if isinstance(value, FunctionType) and value.__module__ == p.audit.__name__:
            ns[name] = FunctionType(value.__code__, ns, name, value.__defaults__, value.__closure__)
    ns['pages'] = lambda base, akv, fault: p.pages(base, index, fault)
    ns['outputs'] = lambda name: outputs(index)
    return ns


def native_contract(rows, symbols, phase=0):
    retires = [r for r in rows if r['event'] == 'retire']
    require(retires and [int(r['order']) for r in retires] == list(range(len(retires))), 'Complete contiguous retirements')
    eoc = [r for r in retires if int(r['mem_addr'],16) == 0xd0000000 and int(r['mem_wmask'],16)]
    require(len(eoc) == 1 and int(eoc[0]['mem_wmask'],16) == 255
        and int(eoc[0]['mem_wdata'],16) == 0 and not int(eoc[0]['trap'])
        and int(eoc[0]['pc'],16) == symbols['_eoc']+8, 'Exact native CRT successful EOC store, not Spike tohost')
    tail = [r for r in retires if int(r['order']) > int(eoc[0]['order'])]
    require(len(tail) < 64 and all(not int(r['trap']) and int(r['mem_wmask'],16) == 0
        and int(r['pc'],16) in (symbols['_eoc'],symbols['_eoc']+4,symbols['_eoc']+12)
        for r in tail), 'Only bounded CRT terminal loop after EOC')
    traps = [r for r in retires if int(r['trap'])]
    require([(int(r['pc'],16),int(r['insn'],16)) for r in traps] ==
        [(symbols['akvc%d_s_exit'%phase],0x73)], 'Only S ECALL retires as trap')
    # Faulting custom operations return exceptions, but do not retire.
    for i in (phase,):
        pre = 'akvc%d_' % i
        begins = [int(r['cycle']) for r in retires if int(r['pc'],16) == symbols[pre+'s_begin']]
        ends = [int(r['cycle']) for r in retires if int(r['pc'],16) == symbols[pre+'restore_end']]
        require(len(begins) == len(ends) == 1 and begins[0] < ends[0], 'Unique phase/ledger interval')
        ledger = {}; start = symbols[pre+'records']
        for r in retires:
            if not begins[0] <= int(r['cycle']) <= ends[0]: continue
            addr = int(r['mem_addr'],16)
            if start <= addr < start+192 and int(r['mem_wmask'],16):
                require(int(r['mem_wmask'],16) == 255 and not int(r['trap']), 'Ledger exact SD')
                require(addr not in ledger, 'Duplicate trap ledger write')
                ledger[addr] = int(r['mem_wdata'],16)
        require(set(ledger) == set(range(start,start+192,8)), 'Full unique trap ledger')
        for j, (cause, pc, tval) in enumerate(((13,symbols[pre+'site'],p.ADDRESSES[i]),(9,symbols[pre+'s_exit'],0))):
            expected = {0:cause,1:pc,2:tval,4:(8<<60)|(0x71<<44)|(symbols[pre+'pages']>>12),
                5:16,6:24,7:0,8:5,9:0,10:j+1,11:1}
            require(all(ledger[start+j*96+k*8] == v for k,v in expected.items()), 'Exact custom PC/tval/CSR ledger')
            require(ledger[start+j*96+24] & 0x7e7faa == 0x6e00, 'Exact S trap privilege state')
    return dict(retirements=len(retires), last_cycle=max(int(r['cycle']) for r in rows),
        traps=2, scalar_policy='Complete independent PTE/source/VRF/guards readback and CSR/trap owner; not a scalar ISA stream equality claim')


def architecture(run, output, symbols, phase=0):
    with (run/'commit_trace.csv').open(newline='') as stream:
        reader = csv.DictReader(stream); fields = reader.fieldnames; rows = list(reader)
    result = native_contract(rows, symbols,phase); owners = []
    with (run/'vector_trace.csv').open(newline='') as stream:
        vector_reader = csv.DictReader(stream); vector_fields = vector_reader.fieldnames; vectors = list(vector_reader)
    lanes,vlen,activities = prior._parse_vector_trace(run/'vector_trace.csv')
    require((lanes,vlen) == (4,1024) and all(w.be & ~w.known_be == 0
        for a in activities.values() for w in a.writes), 'All enabled native VRF bytes known')
    for i in (phase,):
        prefix = 'akvc%d_' % i
        starts = [int(r['cycle']) for r in rows if r['event']=='retire' and int(r['pc'],16)==symbols[prefix+'s_begin']]
        ends = [int(r['cycle']) for r in rows if r['event']=='retire' and int(r['pc'],16)==symbols[prefix+'restore_end']]
        require(len(starts) == len(ends) == 1 and starts[0] < ends[0], 'Exact phase boundaries')
        lo, hi = starts[0], ends[0]
        commit = output/('phase%d-commit.csv'%i); vector = output/('phase%d-vector.csv'%i)
        for path, names, data in ((commit,fields,rows),(vector,vector_fields,vectors)):
            with path.open('x',newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=names); writer.writeheader()
                writer.writerows(r for r in data if r['event']=='config' or lo <= int(r['cycle']) <= hi)
        info = dict(symbols={'gap71_'+key[len(prefix):]:value for key,value in symbols.items() if key.startswith(prefix)},
            words=dict(gap71_site=0x00b5205b,gap71_load_site=0x0005345b,gap71_release_site=0x0000505b))
        owners.append(owner_oracle(i)['runtime_traces'](commit,vector,'gap71_akv_fault',info))
    result['owners'] = owners
    return result


def cycle_gate(samples, last_cycle=0, addresses=None):
    addresses = p.ADDRESSES if addresses is None else addresses
    outstanding = deque(); held = None; faults = []; acknowledged = []; retries = set()
    ar = rlast = ticks = 0; idle = False
    for time, sample in samples:
        def v(name):
            value = sample.get(name)
            require(type(value) is int and value >= 0, 'Missing/unknown active probe '+name)
            return value
        if not v('rst_ni'):
            require(not faults and not outstanding and ar == 0, 'Unexpected active reset')
            ticks = 0; continue
        ticks += 1
        count, pending, stalled = [v(n) for n in ('burst_fifo_count_q','fault_pending_q','ar_stalled_q')]
        av, ready, rv, rr = [v(n) for n in ('axi_ar_valid_o','axi_ar_ready_i','axi_r_valid_i','axi_r_ready_o')]
        require(count == len(outstanding), 'AR/RLAST outstanding count')
        require(v('fault_valid_o') == int(bool(pending and count == 0 and not stalled)), 'Fault must wait for complete drain')
        require(v('response_fault_event') == v('response_drain_q') == 0, 'Unexpected AXI error')
        addr = v('axi_ar_o.addr') if av else None
        if held is not None: require(av and addr == held, 'Held AR changed')
        if pending and av: require(stalled and held is not None, 'New AR while fault pending')
        held = addr if av and not ready else None
        if v('planner_fault_event'):
            index = len(faults); require(index < len(addresses), 'Extra planner fault')
            a = addresses[index]
            require(v('en_ld_st_translation_i') == 1 and v('plan_state_q') == 2
                and v('mmu_req_o') == 1 and v('mmu_vaddr_o') == a
                and v('mmu_exception_valid_i') == 1 and v('mmu_exception_i.cause') == 13
                and v('mmu_exception_i.tval') == a and v('planner_fault_kind') == 2
                and v('planner_fault_vaddr') == a and v('planner_fault_tag.role') == 2
                and v('physical_check_valid_o') == 0 and not av, 'Exact K MMU fault / suppressed AXI')
            for name in sorted(k for k in sample if k.startswith('mmu_exception_i.')):
                require(v(name) == v(name.replace('mmu_exception_i.','planner_fault_mmu_exception.')), 'Full planner exception copy')
            faults.append(dict(time=time,address=hex(a),outstanding=count))
        if v('fault_valid_o'):
            require(faults and len(acknowledged) < len(faults), 'Fault without unique planner owner')
            a = int(faults[-1]['address'],16)
            require(v('fault_kind_o') == 2 and v('fault_vaddr_o') == a
                and v('fault_mmu_exception_o.cause') == 13 and v('fault_mmu_exception_o.tval') == a
                and not av, 'Exact output MMU exception')
            if v('fault_ready_i'): acknowledged.append(time)
        if v('mmu_req_o') and v('mmu_exception_valid_i'):
            require(not v('physical_check_valid_o'), 'Exception leaked to PMA')
        if v('mmu_req_o') and v('mmu_vaddr_o') in addresses and v('mmu_valid_i') and not v('mmu_exception_valid_i'):
            index = addresses.index(v('mmu_vaddr_o'))
            require(len(acknowledged) > index and v('physical_check_valid_o') and v('physical_range_allowed_i'), 'Retry lacks prior fault / mapped PMA')
            retries.add(index)
        if av and ready:
            require(addr < 0x80200000 and addr >= 0x80000000, 'Physical read outside frozen RAM')
            outstanding.append(addr); ar += 1
        if rv and rr:
            require(outstanding and v('axi_r_i.resp') in (0,1), 'Orphan/error read response')
            if v('axi_r_i.last'): outstanding.popleft(); rlast += 1
        idle = not outstanding and not pending and not av and v('plan_state_q') == 0
    require(len(faults) == len(acknowledged) == len(addresses) and retries == set(range(len(addresses))) and idle
        and ar == rlast > 0 and ticks > last_cycle, 'Complete two faults/retries/terminal waveform')
    return dict(status='PASS', faults=faults, acknowledgements=acknowledged,
        accepted_AR=ar, accepted_RLAST=rlast, sampled_edges=ticks, per_beat_length_checked=False)


def cycle_wave(path,last_cycle,phase):
    parse = FunctionType(prior.wave.vcd.__code__,dict(prior.wave.vcd.__globals__,ROOT=runner.SCOPE,WIDTHS={'clk_i':1,'rst_ni':1}))
    iterator = iter(parse(path)); _, declarations = next(iterator)
    names = {k[len(runner.SCOPE)+1:]:v for k,v in declarations.items() if k.startswith(runner.SCOPE+'.')}
    for name in runner.PROBE_NAMES:
        require(name in names or any(k.startswith(name+'.') for k in names), 'Missing exact probe '+name)
    for name in ('mmu_exception_i','planner_fault_mmu_exception','fault_mmu_exception_o'):
        require(names.get(name+'.tval',{}).get('width') == 64 and names.get(name+'.cause',{}).get('width') == 64, 'Exception shape')
    def frames():
        clk = names['clk_i']['code']
        for time,before,after in iterator:
            if before.get(clk) != '0' or after.get(clk) != '1': continue
            sample = {}
            for name,item in names.items():
                bits = before.get(item['code'],'x')
                sample[name] = int(bits,2) if set(bits) <= set('01') else None
            yield time,sample
    return cycle_gate(frames(),last_cycle,(p.ADDRESSES[phase],))


def terminal_gate(status,started,manifest,run):
    require(status.get('status') == 'SIMULATION_EXITED_NOT_ADMITTED' and type(status.get('returncode')) is int
        and status['returncode'] == 0 and status.get('timeout') is False, 'Actual terminal0/no timeout')
    require(status['pid'] == started['pid'] and type(started['pid']) is int and started['pid'] > 0
        and started['command'] == manifest['command'] == runner.command(run,manifest['phase'])
        and started['budget_s'] == runner.BUDGET and started['input_elf'] == str(runner.elf_path(manifest['phase']))
        and started['elf_sha256'] == manifest['elf_sha256']
        and started['image_sha256'] == manifest['image_sha256'], 'Exact native process/command/ELF')


def collect(run, seal, output):
    require(output.parent == life.OUT and not output.exists(), 'Fresh offline output')
    record = run.with_name(run.name+'.prepared.json'); manifest = life.read_bound(record,seal)
    phase = manifest['phase']
    require(manifest == runner.prepare(run,phase,existing=True) and life.read_bound(run/'manifest.json',seal) == manifest, 'Executed prepared identity')
    terminal_gate(life.read_bound(run/'simulation-status.json',life.digest(run/'simulation-status.json')),
        json.loads((run/'started.json').read_text()),manifest,run)
    names = ('manifest.json','simulation-status.json','started.json','run.vcs.log','console.log','commit_trace.csv','vector_trace.csv','akv-canonical-kfault.vpd')
    artifacts = [run/n for n in names] + [f for f in (run/'code.vdb').rglob('*') if f.is_file()]
    require(all(f.is_file() and not f.is_symlink() for f in artifacts), 'Complete nonaliased native files')
    require(len(list((run/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))) == 1, 'Single native VDB')
    pins = life.merge_pins(manifest['pins'],life.merge_pins({str(record):seal},p.h.pins(artifacts)))
    log = (run/'run.vcs.log').read_text()
    require(log.count('Core Test *** SUCCESS ***') == 1
        and not re.search(r'(?m)^.*UVM_(?:ERROR|FATAL)(?!\s*:\s*0\s*$)',log)
        and log.count('PASSED: gap71_akv_fault checks=208 errors=0') == 1, 'Complete program/UVM success')
    perf_lines = re.findall(r'(?m)^\[AKV_PERF\].*$',log)
    require(len(perf_lines) == 6, 'Complete AKV command epoch')
    perf = p.audit.runtime_perf('\n'.join(perf_lines),'gap71_akv_fault')
    console = (run/'console.log').read_text().splitlines()
    require([l for l in console if l.startswith('AKV_KFAULT_OBJECT ')] ==
        ['AKV_KFAULT_OBJECT '+runner.SCOPE+'.'+n for n in runner.PROBE_NAMES]
        and console.count('AKV_KFAULT_PROBE_READY') == 1
        and not any(l.startswith('AKV_KFAULT_PROBE_REJECT') for l in console), 'Actual exact probe execution')
    vpd = run/'akv-canonical-kfault.vpd'
    require(0 < vpd.stat().st_size <= 128*1024*1024, 'Complete bounded wave')
    require(life.digest(prior.CONVERTER) == prior.CONVERTER_SHA, 'Pinned converter')
    pins = life.merge_pins(pins,{str(prior.CONVERTER):prior.CONVERTER_SHA})
    output.mkdir()
    try:
        vcd = output/'focused.vcd'
        with (output/'conversion.log').open('x') as stream:
            subprocess.run([str(prior.CONVERTER),'+splitpacked',str(vpd),str(vcd)], stdout=stream,
                stderr=subprocess.STDOUT,check=True,timeout=120)
        require(vcd.stat().st_size <= 1024*1024*1024, 'Bounded converted evidence')
        pre = life.read_bound(runner.PRE,runner.PRE_SHA)
        arch = architecture(run,output,pre['phases'][phase]['dut']['symbols'],phase)
        cycles = cycle_wave(vcd,arch['last_cycle'],phase)
        life.check(pins)
        life.save(output/'qualification.json',dict(status='AKV_CANONICAL_KFAULT_EXACT_OWNER_ARCH_CYCLE_PASS_NOT_ADMITTED',
            architecture=arch,cycles=cycles,perf=perf,input_pins=pins,output_pins=p.h.pins(output.iterdir()),
            coverage_admitted=False, scalar_Spike_instruction_stream_equality=False,
            actual_raw_gain=None, RTL_modified=False))
    except Exception as error:
        life.save(output/'failure.json',dict(reason=str(error),coverage_admitted=False)); raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True); parser.add_argument('--seal',required=True)
    parser.add_argument('--output',type=Path,required=True); args = parser.parse_args()
    collect(args.run.resolve(),args.seal,args.output.resolve())
