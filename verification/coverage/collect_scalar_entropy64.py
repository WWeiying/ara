"""Terminal entropy64 full scalar/native-frame qualification; raw diagnostic only."""
import argparse
from collections import Counter
import csv
import io
import json
from pathlib import Path
import re
import gzip
import xml.etree.ElementTree as ET

import run_scalar_entropy64 as run

life, need, oracle, architecture = run.life, run.need, run.oracle, run.architecture


def terminal(status):
    need(status.get('status') == 'SIMULATION_EXITED_NOT_ADMITTED' and
         type(status.get('returncode')) is int and status['returncode'] == 0 and
         status.get('coverage_admitted') is False, 'Non-success terminal')


def native_frame(rows, symbols):
    retired = [r for r in rows if r['event'] == 'retire']
    need(retired and [int(r['order']) for r in retired] == list(range(len(retired))), 'Incomplete retirement')
    memory, stores = {}, []
    for r in retired:
        need(int(r['trap']) == 0 and int(r['pc'], 16) != symbols['trap_fail'], 'Native exception')
        item = architecture.scalar_store(r)
        if item is not None:
            address, data = item
            stores.append((address, bytes(data)))
            for i, byte in enumerate(data):
                memory[address+i] = byte
    def value(name, offset=0, size=8):
        address = symbols[name] + offset
        need(all(address+i in memory for i in range(size)), 'Missing native frame byte: ' + name)
        return int.from_bytes(bytes(memory[address+i] for i in range(size)), 'little')
    for phase in range(3):
        for lane in range(8):
            need([value('entropy_results', ((phase*8+lane)*8+i)*8) for i in range(8)] == oracle.gold(phase, lane),
                 'Native independent integer result differs')
    # Require the complete A/B/A write history, not just the final A frame.
    for lane in range(8):
        for word in range(1, 7):
            address = symbols['entropy_memory'] + (lane*8+word)*8
            writes = [int.from_bytes(b, 'little') for a,b in stores if a == address and len(b) == 8]
            expected = [oracle.words(p, lane)[word] for p in range(3)]
            need(writes[-3:] == expected, 'Missing/reordered full phase data writes')
        need([value('entropy_memory', (lane*8+w)*8) for w in range(8)] == oracle.words(2, lane),
             'Native source/guard frame differs')
    before, after = [value('entropy_csrs', i*8) for i in range(6)], [value('entropy_csrs', (i+6)*8) for i in range(6)]
    need(before == after, 'Native six CSR preservation differs')
    need([value('g75_result', size=4), value('g75_result', 4, 4), value('num_failed', size=4), value('tohost')] ==
         [390, 0, 0, 1], 'Native complete390 checks required')
    terminal_rows = [r for r in retired if int(r['mem_addr'],16) == symbols['tohost'] and int(r['mem_wmask'],16)]
    need(len(terminal_rows) == 1 and terminal_rows[0] == retired[-1], 'Post-terminal/multiple tohost')
    return dict(checks=390, result_bytes=1536, memory_and_guard_bytes=512, csr_bytes=96,
                vector_writes_expected=0, csr_before=before, csr_after=after)


def initial_and_dominance(elf, rows, symbols):
    from elftools.elf.elffile import ELFFile
    with elf.open('rb') as stream:
        e = ELFFile(stream)
        symtab = e.get_section_by_name('.symtab')
        entries = {s.name:s for s in symtab.iter_symbols()}
        frames = {}
        for name, size in (('entropy_results',1536), ('entropy_memory',512), ('entropy_csrs',96)):
            s = entries[name]
            need(s['st_value'] == symbols[name] and s['st_size'] == size, 'ELF frame geometry differs')
            section = e.get_section(s['st_shndx'])
            offset = s['st_value'] - section['sh_addr']
            initial = bytes(size) if section['sh_type'] == 'SHT_NOBITS' else section.data()[offset:offset+size]
            need(len(initial) == size and initial == bytes(size), 'ELF initial frame differs')
            frames[name] = (symbols[name], size)
    initialized, reads = set(), 0
    for r in rows:
        if r['event'] != 'retire':
            continue
        store = architecture.scalar_store(r)
        if store is not None:
            address, data = store
            initialized.update(range(address, address+len(data)))
        word = int(r['insn'],16)
        if word & 3 == 3:
            operation = architecture.spike_trace._scalar_memory_access(word)
        else:
            access = run.compressed.decode(word)
            operation = (access['kind'],access['size']) if access else None
        if int(r['mem_rmask'],16):
            need(operation is not None and operation[0] == 'read', 'Unknown native memory read encoding')
        if not operation:
            continue
        # The parser's contract is (kind, width); stores are already accounted above.
        kind, width = operation
        if kind != 'read':
            continue
        address = int(r['mem_addr'],16)
        if any(base <= address < base+size for base,size in frames.values()):
            need(all(address+i in initialized for i in range(width)), 'Frame read before real native initialization')
            reads += 1
    need(reads > 0, 'No native frame reads')
    return dict(ELF_initial_zero_verified=True, native_first_read_store_dominance=True, frame_reads=reads,
                ELF_initialization_not_assumed_to_initialize_hardware=True)


def lifecycle(rows, vectors, console):
    starts, pending, requests, responses = {}, {}, [], []
    retire = [r for r in rows if r['event'] == 'retire']
    csr_retired = [r for r in retire if int(r['insn'],16) & 127 == 0x73 and
                   int(r['insn'],16) >> 20 in (0x8,0xf)]
    need(len(csr_retired) == 4, 'Exact four forwarded CSR retirements required')
    bound_retire = {}
    for r in rows:
        event, tid = r['event'], int(r['trans_id'])
        if event == 'arch_start':
            seq = int(r['order'])
            need(seq not in starts and tid not in pending, 'Duplicate/live transaction')
            insn = int(r['insn'],16)
            need(insn & 127 == 0x73 and (insn >> 12) & 7 == 2 and (insn >> 15) & 31 == 0 and
                 insn >> 20 in (0x8,0xf), 'Foreign/non-readonly forwarded CSR')
            starts[seq] = r
            index = len(starts)-1
            need(index < len(csr_retired) and csr_retired[index]['insn'] == r['insn'] and
                 int(r['cycle']) <= int(csr_retired[index]['cycle']), 'CSR start/retirement identity or time differs')
            bound_retire[seq] = csr_retired[index]
            pending[tid] = [seq, False]
        elif event == 'cvx_req':
            need(tid in pending and pending[tid][1] is False, 'Orphan/duplicate request')
            seq = pending[tid][0]
            need(r['insn'] == starts[seq]['insn'], 'Request opcode differs')
            pending[tid][1] = True
            requests.append(seq)
        elif event == 'cvx_resp':
            need(tid in pending and pending[tid][1] and int(r['trap']) == 0, 'Orphan/duplicate/exception response')
            seq = pending.pop(tid)[0]
            need(int(starts[seq]['cycle']) <= int(r['cycle']) <= int(bound_retire[seq]['cycle']),
                 'CSR response outside exact corresponding retirement')
            responses.append(seq)
        else:
            need(event == 'retire', 'Unexpected scalar backend event')
    need(not pending and len(starts) == 4 and Counter(requests) == Counter(starts.keys()) == Counter(responses),
         'Four readonly CSR lifecycle conservation differs')
    need(all(r['event'] == 'config' for r in vectors), 'Unexpected VRF/backend activity')
    matches = re.findall(r'^\[ARA_CONTRACT\] requests=(\d+) responses=(\d+) exceptions=(\d+) mmu_request_cycles=(\d+) '
        r'protocol_errors=(\d+) outstanding=(\d+) req_stalled=(\d+) resp_stalled=(\d+)\s*$', console, re.M)
    need(len(matches) == 1 and tuple(map(int,matches[0])) == (4,4,0,0,0,0,0,0), 'Exact frozen contract differs')
    need(console.count('Core Test *** SUCCESS ***') == 1, 'Missing/duplicate Core success')
    for line in console.splitlines():
        if 'UVM_ERROR' in line or 'UVM_FATAL' in line:
            need(re.fullmatch(r'\s*UVM_(?:ERROR|FATAL)\s*:\s*0\s*',line) is not None, 'UVM error/fatal')
    return dict(requests=4, responses=4, no_vector_writes=True, trap_events=0,
                next_request_is_not_retirement_deadline=True, UVM_final_summary_not_claimed=True)


def scoped_sample(path, definitions):
    binary, _ = run.toggle.rows(path, run.SCOPES)
    intervals = {}
    with gzip.open(path,'rb') as stream:
        for _, node in ET.iterparse(stream, events=('end',)):
            if node.tag == 'instance_intervaldata' and node.get('name') in run.SCOPES:
                scope = node.get('name')
                need(scope not in intervals and node.get('chksum') == definitions[scope]['checksum'], 'MDA identity differs')
                groups = run.mda.intervals(node.get('value',''))
                arrays = [n for n in ET.fromstring(definitions[scope]['shape']).find('tglshape') if n.tag == 'arrays']
                need(len(arrays) == len(groups) and sorted(run.mda.dimensions(n)[1] for n in arrays) ==
                     sorted(g['extent'] for g in groups), 'Typed MDA array extent universe differs')
                intervals[scope] = groups
            node.clear()
    need(set(intervals) == set(run.SCOPES), 'Missing typed MDA scope')
    need(all(binary[s]['checksum'] == definitions[s]['checksum'] for s in run.SCOPES), 'Binary checksum differs')
    return binary, intervals


def measure(out, runtime, run_dir, pins):
    ledger = runtime['input_ledger']
    before = json.loads((run.BASE / 'combined-bits.json').read_bytes())
    need(ledger == [ledger[0], *before['tests']] and len(before['tests']) == 786, 'Baseline membership changed')
    vdb = run_dir / 'code.vdb'
    need(str(vdb) not in before['tests'], 'Duplicate candidate VDB')
    path = out / 'single-inputs.txt'
    path.write_text(ledger[0]+'\n'+str(vdb)+'\n')
    single = run.bitmap.collect(path)
    after = run.bitmap.combine(before, single)
    need(len(after['tests']) == len(set(after['tests'])) == 787 and after['tests'][:-1] == before['tests'], 'Prefix lost')
    need(sum(len(x) for x in before['metrics'].values()) == 6162, 'Incomplete metric universe')
    for metric, scopes in before['metrics'].items():
        need(set(scopes) == set(single['metrics'][metric]) == set(after['metrics'][metric]), 'Metric universe differs')
        for scope, old in scopes.items():
            new, merged = single['metrics'][metric][scope], after['metrics'][metric][scope]
            need((old['width'],old['checksum']) == (new['width'],new['checksum']), 'Metric identity differs')
            need(int(merged['bits'],16) == int(old['bits'],16) | int(new['bits'],16), 'Independent OR differs')
    merged = None
    for i, member in enumerate(ledger[1:]):
        files = list((Path(member)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        need(len(files) == 1 and str(files[0]) in pins, 'Unbound/ambiguous baseline Toggle')
        binary, _ = scoped_sample(files[0], runtime['compiled_definitions'])
        merged = binary if merged is None else run.toggle.union(merged,binary)
        if i % 100 == 0:
            print('Scoped baseline Toggle %d/786' % (i+1), flush=True)
    files = list((vdb/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    need(len(files) == 1, 'Ambiguous singleton Toggle')
    binary, intervals = scoped_sample(files[0], runtime['compiled_definitions'])
    union = run.toggle.union(merged,binary)
    gain = run.toggle.gains(merged,union)
    for name, obj in (('single-bits.json',single), ('combined-bits.candidate.json',after),
        ('raw-delta.json',run.bitmap.delta(before,after)), ('typed-toggle.json',dict(before=merged,single=binary,
        after=union,new_serialized_positions=gain,singleton_MDA_intervals=intervals,
        interval_code_direction_semantics_unknown=True,MDA_gain_not_counted=True,official_percentage=False))):
        life.save(out/name,obj)


def collect(run_dir, seal, out):
    need(out.parent == run.OUT and not out.exists(), 'Fresh direct qualification output only')
    record = Path(str(run_dir)+'.prepared.json')
    runtime = life.read_bound(record,seal)
    need(runtime['command'] == run.make_command(run_dir,runtime['preflight']) and runtime['timeout_s'] == 600,
         'Prepared command/budget differs')
    pins = life.merge_pins(runtime['pins'],{str(record):seal})
    check = run.check
    check(pins)
    need(json.loads((run_dir/'manifest.json').read_bytes()) == runtime, 'Executed/prepared semantic contract differs')
    terminal(json.loads((run_dir/'simulation-status.json').read_bytes()))
    for p in run_dir.rglob('*'):
        if p.is_file():
            pins = life.merge_pins(pins,{str(p):run.toggle.digest(p)})
    out.mkdir()
    try:
        pre = runtime['preflight']
        commits = oracle.build.parse_spike_commits(run.PRE/'spike.trace')
        need(oracle.validate(commits,pre['symbols']) == pre['counts'], 'Sealed reference replay differs')
        commits = run.reference_interval(commits,pre['symbols'])
        rows = list(csv.DictReader((run_dir/'commit_trace.csv').open()))
        vectors = list(csv.DictReader((run_dir/'vector_trace.csv').open()))
        scalar = architecture.spike_trace.compare_commit_prefix(run.PRE/'spike.trace',run_dir/'commit_trace.csv',
            0x80000000,terminal_tohost_address=pre['symbols']['tohost'],rvfi_store_data_layout='unshifted')
        life.save(out/'scalar-comparison.json',scalar)
        counts = architecture.reference_counts(commits,pre['symbols'])
        need(counts == runtime['reference_interval_counts'], 'Reviewed complete prefix counts differ')
        architecture.scalar_exact(scalar,counts)
        native = native_frame(rows,pre['symbols'])
        initial = initial_and_dominance(run.PRE/'input.elf',rows,pre['symbols'])
        control = lifecycle(rows,vectors,(run_dir/'console.log').read_text())
        need(lifecycle(rows,vectors,(run_dir/'run.vcs.log').read_text()) == control, 'Log contract copies differ')
        for name,obj in (('native-frame.json',native),('ELF-native-initialization.json',initial),('lifecycle.json',control)):
            life.save(out/name,obj)
        measure(out,runtime,run_dir,pins)
        check(pins)
        life.save(out/'evidence-pins.json',pins)
        outputs = {str(p):run.toggle.digest(p) for p in out.iterdir() if p.is_file()}
        life.save(out/'qualification.json',dict(status='SCALAR_ENTROPY64_ARCHITECTURE_AND_RAW_DIAGNOSTIC_NOT_ADMITTED',
            input_pins=pins,output_pins=outputs,baseline=786,architecture_pass=True,
            scalar_counts=counts,coverage_admitted=False,MDA_direction_gain_qualified=False,official_DVE_percentage=False))
    except Exception as error:
        life.save(out/'failure.json',dict(reason=str(error),coverage_admitted=False))
        raise


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--seal',required=True)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    collect(a.run.absolute(),a.seal,a.output.absolute())
