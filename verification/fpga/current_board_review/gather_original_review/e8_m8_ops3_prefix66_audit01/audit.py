#!/usr/bin/env python3
"""Independent e8 vi31 audit, derived from own e16 auditor; no simulation."""
import difflib
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
PREP = OUT.parent / 'e8_m8_ops3_prefix66_prepare01'
ROOT = OUT.parents[4]
NAME = 'gather_prefix_e8_m8_ops3'
CAMPAIGN = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
PART = CAMPAIGN / 'rvv_permute_partitions01'
CHILD = 'rvv_permute_restart_e8_m8_ops3'
OBJ = ROOT / 'install/riscv-gcc/bin/riscv64-unknown-elf-objdump'


def need(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            digest.update(chunk)
    return digest.hexdigest()


def asm(path):
    text = subprocess.check_output([str(OBJ), '-d', str(path)], text=True)
    rows = []
    for line in text.splitlines():
        m = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]+)\s+(.+)', line)
        if m:
            rows.append(dict(pc=int(m[1], 16), insn=m[2], text=m[3]))
    return rows


def independent_model():
    state = 0xe736815b449aec21
    data, indices, indices16 = [], [], []
    for i in range(1024):
        state ^= (state << 13) & 0xffffffffffffffff
        state ^= state >> 7
        state ^= (state << 17) & 0xffffffffffffffff
        data.append(state & 0xff)
        index = [0, 1, 1023, 1024, 1025, state % 1056][i % 6]
        indices.append(index & 255)
        indices16.append(index)
    rows = []
    # The first66 calls never leave seed0/scalar-slot0 of the selected child.
    for li, vl in enumerate([0, 1, 2, 3, 512, 1023, 1024]):
        for mode in range(4):
            mask = [mode == 0 or (mode == 1 and i % 2 == 1) or
                    (mode == 2 and i % 7 == 2) for i in range(1024)]
            pred = [sum(int(mask[8*b+j]) << j for j in range(8))
                    for b in range(128)]
            for trial, start in enumerate([1, vl // 2, vl if vl <= 1023 else 1023, 1023]):
                result = [91] * 1024
                for i in range(start, vl):
                    if mask[i]:
                        result[i] = data[31]
                rows.append(dict(ordinal=len(rows)+1, tuple=[0,3,0,li,mode,trial],
                                 vl=vl, vstart=start, scalar=0,
                                 predicate=pred, output=result))
                if len(rows) == 66:
                    return data, indices, indices16, rows


def verify_preparation():
    ready = read(PREP / 'READY.json')
    need(sha(PREP / 'READY.json') ==
         'b15c7b86fa273aacbc464dca171a3cee3bc4140e701ed639ef70d7cc9aee5388', 'READY identity')
    pins = {}
    for table in (ready['evidence_pins'], read(PREP / 'baseline_pins.json')):
        for name, digest in table.items():
            need(name not in pins or pins[name] == digest, 'Conflicting pins')
            pins[name] = digest
    for name, digest in pins.items():
        if Path(name) != PREP / 'reference/commits.log':
            need(sha(Path(name)) == digest, 'Pin changed: ' + name)
    original = PREP / 'prepared' / NAME / 'original'
    manifest = read(PART / 'manifest.json')
    case, = [x for x in manifest['cases'] if x['name'] == CHILD]
    rec, = [x for x in read(CAMPAIGN / 'stall_family_triage02/triage.json')['cases']
            if x['name'] == CHILD]
    need(case == read(original / 'case.json')['case'] and
         case['operation_ids'] == [3] and case['configurations'] == 2688 and
         case['sew'] == 8 and case['lmul'] == 'm8', 'Original selection')
    need('rvv_recovery08_173' in rec['report'], 'Wrong archived scene')
    need(rec['last_trial'] is None and sha(Path(rec['report'])) == rec['report_sha256'],
         'Archive report/unknown tuple')
    need(sha(original / 'original_linux.elf') == case['sha256'] == rec['elf_sha256'] ==
         sha(PART / 'release/binaries' / CHILD) == sha(Path(rec['report']).parent / CHILD), 'ELF provenance')
    need(case['sha256'] == 'ef3a7ff6d6dc48a7e5f20adbb7954490c08c7cbbdcd03afe9bbd4859dee7580c', 'Archived e8 ELF')
    need(sha(original / 'scenario.c') == manifest['source_sha256']['permutation_oracle.c'], 'C provenance')
    for file in ['operations.S', 'operations.h']:
        need((original / file).read_bytes() == (PART / CHILD / file).read_bytes(), 'Assembly/header copy')
    sys.path.insert(0, str(OUT.parent))
    sys.path.insert(0, str(OUT.parent.parent / 'integration'))
    from prepare import adapt
    source = (original / 'scenario.c').read_text()
    adapted = adapt(source, NAME)
    anchor = '            ++cases;\n'
    need(adapted.count(anchor) == 1, 'Unique prefix anchor')
    port = adapted.replace(anchor, anchor + '            if(cases==66)goto prefix_done;\n')
    anchor = '    text(errors ? "RVV_PERMUTE_FAIL sew=":"RVV_PERMUTE_PASS sew=");'
    need(port.count(anchor) == 1, 'Unique finish anchor')
    port = port.replace(anchor, 'prefix_done:\n    if(cases!=66)++errors;\n'
                        '    text(errors ? "RVV_GATHER_PREFIX_FAIL sew=":"RVV_GATHER_PREFIX_PASS sew=");')
    need(port == (PREP / 'prepared' / NAME / 'case.c').read_text(), 'Source adaptation')
    for label, before, after in [('adapter', source, adapted), ('prefix', adapted, port)]:
        diff = ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                       fromfile=label+'_before', tofile=label+'_after'))
        need(diff == (PREP / 'source_diffs' / (label+'.diff')).read_text(), 'Recorded diff differs')
    proof = read(PREP / 'source_elf_proof.json')
    codes = [x['insn'] for x in proof['original_routine']]
    need(len(codes) == 13 and codes[8] == '308fbc57' and
         proof['original_routine'][8]['pc'] == 0x1063e, 'Original vi31 helper contract')
    for kind, elf in [('original', original / 'original_linux.elf')]+[
            (k, Path(proof[k+'_elf']['path'])) for k in ['soc', 'spike']]:
        dis = asm(elf)
        windows = [dis[i:i+13] for i in range(len(dis)-12)
                   if [x['insn'] for x in dis[i:i+13]] == codes]
        need(len(windows) == 1 and windows[0] == proof[kind+'_routine'], 'Actual ELF helper ' + kind)
    host = read(PREP / 'host/host_gate.json')
    need([x['injection'] for x in host['tests']] ==
         ['none','active','prestart','inactive','tail','guard0','guard1','vstart'], 'Host membership')
    for row in host['tests']:
        log = PREP / 'host' / (row['injection']+'.log')
        need(sha(log) == row['log_sha256'] and row['status'] == 'PASS', 'Host raw pin')
        rc = 0 if row['injection'] == 'none' else 1
        need(row['returncode'] == rc and
             f'HOST_PREFIX_CALLS=66 INJECTED={rc}' in log.read_text() and
             f'RVV_GATHER_PREFIX_{"PASS" if rc == 0 else "FAIL"} sew=8 cases=66 errors={rc}'
             in log.read_text(), 'Host raw outcome')
    negatives = read(PREP / 'audit01/audit.json')['raw_trace_negative_results']
    need(len(negatives) == 5 and all(x['status'] == 'REJECTED_AS_EXPECTED' and
         sha(PREP / 'audit01' / (x['name']+'.trace')) == x['sha256'] for x in negatives), 'Offline negatives')
    return ready, proof, pins


def parse_once(proof):
    data, indices, indices16, gold = independent_model()
    recorded_model = read(PREP / 'host_expected.json')
    need(gold == recorded_model['rows'] and data == recorded_model['input'] and
         indices == recorded_model['indices'] and indices16 == recorded_model['indices16'], 'Independent oracle disagrees')
    shim = (PREP / 'host/shim.c').read_text()
    for name, expected in [('data', data), ('indices', indices),
                           ('vl', [g['vl'] for g in gold]),
                           ('start', [g['vstart'] for g in gold]),
                           ('masks', [v for g in gold for v in g['predicate']]),
                           ('output', [v for g in gold for v in g['output']])]:
        match = re.search(r'gold_' + name + r'\[\]=\{([^}]+)\}', shim)
        need(match and [int(v) for v in match[1].split(',')] == expected,
             'Host static fixture differs: ' + name)
    ref = read(PREP / 'reference/reference.json')
    routine = proof['spike_routine']
    lookup = {x['pc']:i for i,x in enumerate(routine)}
    elf = Path(proof['spike_elf']['path'])
    symbols = subprocess.check_output([str(OBJ), '-t', str(elf)], text=True)
    addresses = {}
    for line in symbols.splitlines():
        fields = line.split()
        if fields and fields[-1] in ['input','indices','indices16','predicate','output','replay_log','tohost']:
            addresses[fields[-1]] = int(fields[0],16)
    need({k:hex(v) for k,v in addresses.items()} == ref['addresses'], 'Actual ELF symbols')
    regs, memory, vectors, csr = {0:0}, {}, {}, {}
    calls, counts, checks = [], [0]*13, 0
    current, step, retired, exited = None, 0, 0, False
    console = bytearray(8192)
    header = re.compile(r'core\s+0:\s+\d\s+(0x[0-9a-f]+)\s+\((0x[0-9a-f]+)\)(.*)')
    integer = re.compile(r'\bx(\d+)\s+0x([0-9a-f]+)')
    vector = re.compile(r'\bv(\d+)\s+0x([0-9a-f]+)')
    csrs = re.compile(r'\bc\d+_(vstart|vl|vtype)\s+0x([0-9a-f]+)')
    mem = re.compile(r'\bmem\s+0x([0-9a-f]+)(?:\s+0x([0-9a-f]+))?')
    digest = hashlib.sha256()
    vector_pcs = {}

    def group(first):
        raw = b''.join(vectors[n].to_bytes(128,'little') for n in range(first,first+8))
        return list(raw)

    def finish():
        if current is not None:
            need(step == 0 and current['seen'] == set(range(1026)), 'Full scalar oracle incomplete')
            current.pop('seen')

    with (PREP / 'reference/commits.log').open('rb') as stream:
        for lineno, raw in enumerate(stream, 1):
            digest.update(raw)
            line = raw.decode('ascii')
            need('trap_' not in line, 'Unexpected reference trap')
            m = header.match(line)
            if not m or exited:
                continue
            pc, code, rest = int(m[1],16), int(m[2],16), m[3]
            if pc < 0x80000000:
                continue
            retired += 1
            if code & 127 == 87:
                key = f'{pc:x}:{code:08x}'
                vector_pcs[key] = vector_pcs.get(key, 0) + 1
            rd = integer.search(rest)
            accesses = [(int(a,16), int(b,16) if b else None) for a,b in mem.findall(rest)]
            if code & 127 == 35:
                width = 1 << ((code >> 12) & 7)
                need(width <= 8, 'Scalar store width')
                for address, value in accesses:
                    need(value is not None, 'Scalar store lacks value')
                    for b in range(width):
                        memory[address+b] = (value >> (8*b)) & 255
                    if width == 1 and addresses['replay_log'] <= address < addresses['replay_log']+8192:
                        console[address-addresses['replay_log']] = value & 255
            i = lookup.get(pc)
            if i is not None:
                need(i == step and code == int(routine[i]['insn'],16), f'Helper order/encoding at {lineno}')
                if i == 0:
                    finish()
                    j = len(calls)
                    need(j < 66, 'Extra call')
                    g = gold[j]
                    args = [addresses['input'], addresses['indices'], addresses['output']+1,
                            g['vl'], 1024, addresses['predicate'], 0, g['vstart']]
                    need([regs.get(n) for n in range(10,18)] == args, 'Arguments/history differ')
                    for name, values, width in [('input',data,1), ('indices',indices,1),
                            ('indices16',indices16,2), ('predicate',g['predicate'],1), ('output',[91]*1026,1)]:
                        for k, value in enumerate(values):
                            start = addresses[name]+k*width
                            actual = bytes(memory[start+b] for b in range(width))
                            need(int.from_bytes(actual,'little') == value, 'Initialization ' + name)
                    current = dict(ordinal=j+1, tuple=g['tuple'], vl=g['vl'], vstart=g['vstart'],
                                   seen=set(), setup_values=4226)
                    calls.append(current)
                if i in (0,5,10):
                    need(rd and int(rd[1]) == 5 and int(rd[2],16) == (g['vl'] if i == 5 else 1024), 'vset return')
                if i == 8:
                    need(csr.get('vl') == g['vl'] and csr.get('vstart') == g['vstart'] and
                         csr.get('vtype') == 3, 'Target architectural CSR')
                    need(group(8) == data and group(16) == indices and group(24) == [91]*1024, 'Target full vectors')
                    need(vectors[0] & ((1 << 1024)-1) == int.from_bytes(bytes(g['predicate']),'little'), 'Target predicate')
                    need((code >> 12) & 7 == 3 and (code >> 15) & 31 == 31 and
                         (code >> 25) & 1 == 0 and code >> 26 == 12,
                         'Actual masked OPIVI unsigned31 encoding')
                    need(regs.get(28) == 0 and regs.get(16) == 0,
                         'Original unused scalar/move not retained')
                    need(group(8)[31] == data[31] == 177 and data[0] == 185,
                         'Independent actual source31 discriminator')
                    current.update(target_retired=retired, target_line=lineno,
                                   actual_source31=group(8)[31], immediate_unsigned=31,
                                   body_nonempty=g['vstart'] < g['vl'],
                                   active_selected_count=sum((g['predicate'][k//8] >> (k%8)) & 1
                                       for k in range(g['vstart'],g['vl'])))
                if i == 9:
                    need(rd and int(rd[1]) == 10 and int(rd[2],16) == 0, 'Returned vstart')
                if i == 11:
                    need(csr.get('vl') == 1024 and group(24) == g['output'], 'Store full vector state')
                    need(accesses == [(addresses['output']+1+k,v) for k,v in enumerate(g['output'])], 'Full vector store')
                counts[i] += 1
                step = (step+1) % 13
            for n,v in vector.findall(rest):
                vectors[int(n)] = int(v,16)
            for name,value in csrs.findall(rest):
                csr[name] = int(value,16)
            if i in (0,5,10):
                need(csr.get('vl') == (g['vl'] if i == 5 else 1024) and csr.get('vtype') == 3,
                     'vset actual VL/vtype state')
            if i == 8:
                need(group(24) == g['output'] and csr.get('vstart') == 0, 'Actual target result/reset')
            if current is not None and code & 127 == 3 and accesses:
                for address, value in accesses:
                    if addresses['output'] <= address < addresses['output']+1026:
                        need(step == 0 and (code >> 12) & 7 == 4 and rd and value is None,
                             'Scalar oracle load contract')
                        index = address-addresses['output']
                        need(index not in current['seen'], 'Duplicate scalar check')
                        want = 91 if index in (0,1025) else g['output'][index-1]
                        need(int(rd[2],16) == want, 'Scalar output/guard differs')
                        current['seen'].add(index)
                        checks += 1
            if accesses == [(addresses['tohost'],1)] and code & 127 == 35:
                finish()
                exited = True
            if rd:
                regs[int(rd[1])] = int(rd[2],16)
    need(exited and len(calls) == 66 and counts == [66]*13 and checks == 67716, 'Incomplete execution')
    need(retired == ref['firmware_retired_to_htif_store'] == 2621149, 'Retirement cost')
    need(digest.hexdigest() == ref['commit_sha256'], 'Single-pass raw identity')
    need(digest.hexdigest() == '3f6fe246594f6957d8fa61b07598ff600673b093d74995f7f4e31777cabb64c0',
         'Expected raw identity')
    need(len(ref['calls']) == len(calls), 'Recorded call count')
    for actual, recorded in zip(calls, ref['calls']):
        need(actual['tuple'] == recorded['original_tuple'] and
             actual['target_retired'] == recorded['target']['retired'] and
             actual['target_line'] == recorded['target']['trace_line'] and
             actual['actual_source31'] == recorded['actual_source31'] == 177 and
             actual['immediate_unsigned'] == recorded['immediate_unsigned'] == 31,
             'Recorded target/history/source31 differs')
    text = console.split(b'\0',1)[0].decode('ascii')
    need(text == ref['reconstructed_console'] == (PREP / 'reference/runtime.log').read_text(), 'Raw console differs')
    for marker in proof['spike_elf']['pass_markers']:
        need(text.splitlines().count(marker) == 1, 'Pass marker count')
    need(not re.search('FAIL|TRAP|MISMATCH|DETAIL|RVV_PERMUTE_PASS',text), 'Failure marker veto')
    execution, command = read(PREP / 'reference/execution.json'), read(PREP / 'reference/command.json')
    need(execution['returncode'] == ref['returncode'] == 0 and execution['command'] == command['command'] and
         execution['elapsed_s'] == ref['elapsed_s'] < 120 and command['instructions'] == 5000000 and
         command['file_bytes'] == 768*1024*1024 and '--isa=rv64gcv_zvl1024b' in command['command'], 'Execution/limits')
    return dict(calls=calls, helper_counts=counts, scalar_checks=checks, fullcap_results=67584,
                guards=132, returned_vstart_checks=66, vset_checks=198, setup_values_per_call=4226,
                full_vector_inputs_predicate_oldvd_checks=66, full_result_vector_checks=66,
                full_vector_store_checks=66, retired=retired, raw_sha256=digest.hexdigest(),
                raw_bytes=(PREP / 'reference/commits.log').stat().st_size,
                console=text, recorded_spike_seconds=execution['elapsed_s'],
                actual_source31=data[31], unused_scalar_register=0, immediate_unsigned=31,
                actual_source0=data[0], arithmetic_vector_pc_counts=vector_pcs,
                active_selected_elements=sum(r['active_selected_count'] for r in calls),
                nonempty_body_calls=[r['ordinal'] for r in calls if r['body_nonempty']],
                active_selected_calls=[r['ordinal'] for r in calls if r['active_selected_count']],
                no_body_calls=[r['ordinal'] for r in calls if not r['body_nonempty']])


def main():
    target = OUT / 'audit.json'
    need(not target.exists(), 'Do not overwrite audit evidence')
    ready, proof, pins = verify_preparation()
    result = parse_once(proof)
    need(result['raw_sha256'] == pins[str(PREP / 'reference/commits.log')], 'Raw evidence pin')
    result.update(status='ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT', ready_sha256=sha(PREP/'READY.json'),
                  evidence_pins=len(ready['evidence_pins']), baseline_pins=ready['baseline_count'],
                  host_results_read_not_rerun=8, offline_negative_results_read_not_rerun=5,
                  auditor_sha256=sha(Path(__file__)), original_stopped_tuple=None,
                  full2688_child_pass=False, linux_replay=False, source_proof=proof)
    with target.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ['calls','source_proof','console']},indent=2))


if __name__ == '__main__':
    main()
