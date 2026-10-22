#!/usr/bin/env python3
"""Read-only source audit and one independent parse of an existing Spike log."""
from collections import Counter
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
PREP = OUT.parent/'merge_original_prefix98_prepare01'
ROOT = OUT.parents[3]
NAME = 'merge_prefix_e16_m8_ops4'
CHILD = 'rvv_permute_restart_e16_m8_ops4'
CAMPAIGN = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
OBJ = ROOT/'install/riscv-gcc/bin/riscv64-unknown-elf-objdump'
READY_SHA = '8381b90ee089c90be273faca67b8096f802f628f655fd5756a186ef57b3ed175'


def need(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for b in iter(lambda: stream.read(1048576), b''):
            h.update(b)
    return h.hexdigest()


def save(name, value):
    with (OUT/name).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def disassemble(elf):
    text = subprocess.check_output([str(OBJ), '-d', '-z', str(elf)], text=True)
    code, functions, current = {}, {}, None
    for line in text.splitlines():
        label = re.fullmatch(r'[0-9a-f]+ <([^>]+)>:', line)
        if label:
            current = label[1]
            functions[current] = []
        m = re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4}(?:[0-9a-f]{4})?)\s+(.+)$', line)
        if m:
            entry = dict(pc=int(m[1], 16), insn=m[2], text=m[3].split('#')[0].strip())
            need(entry['pc'] not in code, 'Duplicate disassembly PC')
            code[entry['pc']] = entry
            functions[current].append(entry)
    raw = elf.read_bytes()
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    need(raw[:6] == b'\x7fELF\x02\x01' and header[2] == 243, 'Not RISC-V ELF64 LE')
    loads = [struct.unpack_from('<IIQQQQQQ', raw, header[5]+i*header[9]) for i in range(header[10])]
    for pc, entry in code.items():
        value = bytes.fromhex(entry['insn'])[::-1]
        segment, = [s for s in loads if s[0] == 1 and s[1]&1 and s[3] <= pc and pc+len(value) <= s[3]+s[5]]
        at = segment[2]+pc-segment[3]
        need(raw[at:at+len(value)] == value, 'ELF bytes differ from disassembly')
    return code, functions


def model():
    state, data, indices = 0xe736815b449aec21, [], []
    for i in range(512):
        state ^= (state << 13) & ((1<<64)-1)
        state ^= state >> 7
        state ^= (state << 17) & ((1<<64)-1)
        data.append(state & 65535)
        indices.append([0, 1, 511, 512, 513, state % 544][i % 6])
    rows = []
    for li, vl in enumerate([0, 1, 2, 3, 256, 511, 512]):
        for mode in range(4):
            bits = [mode == 0 or (mode == 1 and i % 2 == 1) or (mode == 2 and i % 7 == 2)
                    for i in range(512)]
            packed = [sum(int(bits[b*8+j]) << j for j in range(8)) for b in range(64)]+[0]*64
            for trial, start in enumerate([1, vl//2, vl, 511]):
                output = [91]*512
                for i in range(start, vl):
                    output[i] = indices[i] if bits[i] else data[i]
                rows.append(dict(ordinal=len(rows)+1, tuple=[0,4,0,li,mode,trial], vl=vl,
                                 vstart=start, scalar=0, predicate=packed, output=output))
                if len(rows) == 98:
                    return data, indices, rows


def prepare():
    need(sha(PREP/'READY.json') == READY_SHA, 'READY changed')
    ready, proof = read(PREP/'READY.json'), read(PREP/'source_elf_proof.json')
    pins = dict(ready['baseline_pins'])
    for p, h in ready['owned_pins'].items():
        need(p not in pins or pins[p] == h, 'Conflicting pins')
        pins[p] = h
    raw_path = PREP/'reference/commits.log'
    for p, h in pins.items():
        if Path(p) != raw_path:
            need(sha(Path(p)) == h, 'Pin drift: '+p)
    original = PREP/'prepared'/NAME/'original'
    manifest = read(CAMPAIGN/'rvv_permute_partitions01/manifest.json')
    child, = [c for c in manifest['cases'] if c['name'] == CHILD]
    scene, = [c for c in read(CAMPAIGN/'stall_family_triage02/triage.json')['cases'] if c['name'] == CHILD]
    need(child == read(original/'case.json')['case'] and child['operation_ids'] == [4] and
         child['configurations'] == 2688 and child['sew'] == 16 and child['lmul'] == 'm8', 'Original child scope')
    need(scene['last_trial'] is None and 'rvv_recovery08_159' in scene['report'], 'Historical unknown boundary')
    need(sha(original/'scenario.c') == manifest['source_sha256']['permutation_oracle.c'], 'Original C identity')
    need(sha(original/'original_linux.elf') == child['sha256'] == scene['elf_sha256'] ==
         sha(Path(scene['report']).parent/CHILD), 'Original ELF/scene identity')
    prov, = read(PREP/'prepared/provenance.json')['cases']
    need(prov['original_case'] == child and prov['defines'] ==
         ['SEW=16', 'RESTART_PERMUTATIONS=1', 'PERMUTE_OP_MASK=16'], 'Port defines/scope')
    module = importlib.util.spec_from_file_location('immutable_adapt_only', OUT.parent/'integration/prepare.py')
    adapter = importlib.util.module_from_spec(module)
    module.loader.exec_module(adapter)
    source = (original/'scenario.c').read_text()
    adapted = adapter.adapt(source, NAME)
    anchor = '            ++cases;\n'
    marker = '    text(errors ? "RVV_PERMUTE_FAIL sew=":"RVV_PERMUTE_PASS sew=");'
    need(adapted.count(anchor) == adapted.count(marker) == 1, 'Ambiguous prefix anchors')
    port = adapted.replace(anchor, anchor+'            if(cases==98)goto prefix_done;\n')
    port = port.replace(marker, 'prefix_done:\n    if(cases!=98)++errors;\n'
                        '    text(errors ? "RVV_MERGE_PREFIX_FAIL sew=":"RVV_MERGE_PREFIX_PASS sew=");')
    need(port == (PREP/'prepared'/NAME/'case.c').read_text(), 'Only approved source transformations')
    for label, before, after in [('adapter', source, adapted), ('prefix', adapted, port)]:
        diff = ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                      fromfile=label+'_before', tofile=label+'_after'))
        need(diff == (PREP/'source_diffs'/f'{label}.diff').read_text(), 'Diff evidence differs')
    all_asm = {}
    for kind, elf, name in [('original', original/'original_linux.elf', 'op_4'),
                          ('soc', Path(ready['soc_elf']['path']), NAME+'_op_4'),
                          ('spike', Path(ready['spike_elf']['path']), NAME+'_op_4')]:
        code, functions = disassemble(elf)
        # The archived Linux ELF is stripped: recover its unique contiguous13.
        if kind == 'original':
            routine = [code[r['pc']] for r in proof['original_routine']]
            ordered = sorted(code)
            candidates = [ordered[k:k+13] for k in range(len(ordered)-12) if
                          [code[p]['insn'] for p in ordered[k:k+13]] ==
                          [r['insn'] for r in proof['original_routine']]]
            need(candidates == [[r['pc'] for r in routine]], 'Unique archived original13 recovery')
        else:
            routine = functions[name]
        need(len(routine) == 13 and routine == proof[kind+'_routine'], 'Actual13 proof '+kind)
        all_asm[kind] = routine
        if kind == 'spike':
            spike_code, spike_funcs = code, functions
    need([r['insn'] for r in all_asm['original']] == [r['insn'] for r in all_asm['soc']] ==
         [r['insn'] for r in all_asm['spike']], 'Original/SoC/Spike code mismatch')
    need(all_asm['original'][8]['insn'] == '5c880c57', 'Not merge.vvm')
    expected = model()
    recorded = read(PREP/'host_expected.json')
    need(expected[0] == recorded['input'] and expected[1] == recorded['indices'] == recorded['indices16'] and
         expected[2] == recorded['rows'], 'Independent selector/RNG model differs')
    shim = (PREP/'host/shim.c').read_text()
    for name, values in [('data',expected[0]), ('indices',expected[1]),
                         ('vl',[g['vl'] for g in expected[2]]), ('start',[g['vstart'] for g in expected[2]]),
                         ('masks',[v for g in expected[2] for v in g['predicate']]),
                         ('output',[v for g in expected[2] for v in g['output']])]:
        found = re.search(r'gold_'+name+r'\[\]=\{([^}]+)\}', shim)
        need(found and [int(v) for v in found[1].split(',')] == values, 'Host fixture model mismatch '+name)
    return ready, proof, pins, spike_code, spike_funcs, expected, all_asm


def parse(codebook, functions, expected):
    data, indices, gold = expected
    routine, capacity = functions[NAME+'_op_4'], functions[NAME+'_capacity']
    selected = {r['pc']:i for i,r in enumerate(routine)}
    cap_lookup = {r['pc']:i for i,r in enumerate(capacity)}
    unused = {r['pc'] for n, rs in functions.items() if n.startswith(NAME+'_op_') and n != NAME+'_op_4' for r in rs}
    need(len([n for n in functions if n.startswith(NAME+'_op_')]) == 21, 'Expected original21 helpers')
    bootstrap = [r for n in ('_start', 'main', NAME+'_main') for r in functions[n]
                 if r['insn'] in ('00805073','c2202773','c22027f3')]
    need(len(bootstrap) == 3, 'Exact sourced bootstrap CSR inventory')
    bootcsrs = {r['pc']:r for r in bootstrap}
    store, = [r for r in functions['replay_exit'] if r['text'].startswith('sd\t')]
    park, = [r for r in functions['replay_exit'] if r['insn'] == 'a001']
    need(park['pc'] == 0x8000007e and park['text'].startswith('j\t8000007e '), 'Original Spike parking')
    symbols = subprocess.check_output([str(OBJ), '-t', str(PREP/'spike01'/f'{NAME}.elf')], text=True)
    addresses = {s[-1]:int(s[0],16) for line in symbols.splitlines() if (s:=line.split()) and
                 s[-1] in ('input','indices','indices16','predicate','output','replay_log','tohost')}
    rec = read(PREP/'reference/reference.json')
    need({k:hex(v) for k,v in addresses.items()} == rec['addresses'], 'Actual symbol addresses')
    header = re.compile(r'core\s+0:\s+3\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)\n?')
    intreg = re.compile(r'\bx(\d+)\s+0x([0-9a-f]+)')
    vec = re.compile(r'\bv(\d+)\s+0x([0-9a-f]+)')
    csrs = re.compile(r'\bc\d+_(vstart|vl|vtype)\s+0x([0-9a-f]+)')
    mem = re.compile(r'\bmem\s+0x([0-9a-f]+)(?:\s+0x([0-9a-f]+))?')
    boot_expected = [(0x1000,0x297),(0x1004,0x02028593),(0x1008,0xf1402573),(0x100c,0x0182b283),(0x1010,0x28067)]
    regs, memory, vectors, csr = {0:0}, {}, {}, {}
    counts, all_pcs, csr_counts = [0]*13, Counter(), Counter()
    calls, boot = [], []
    step = capstep = caps = retired = total = parking = checks = 0
    exited, current = False, None
    console, digest = bytearray(8192), hashlib.sha256()
    raw_path = PREP/'reference/commits.log'
    before = raw_path.stat()

    def group(first):
        raw = b''.join(vectors[r].to_bytes(128,'little') for r in range(first, first+8))
        return list(struct.unpack('<512H', raw))

    def finish():
        if current is not None:
            need(current['reads'] == set(range(514)) and step == 0 and current['vstart_returned'] == 0,
                 'Incomplete full scalar oracle/guards/CSR')
            del current['reads']

    with raw_path.open('rb') as stream:
        for lineno, raw in enumerate(stream, 1):
            digest.update(raw)
            line = raw.decode('ascii')
            match = header.fullmatch(line)
            need(match is not None and 'trap_' not in line, f'Unparsed/trapped raw line{lineno}')
            pc, insn, rest = int(match[1],16), int(match[2],16), match[3]
            total += 1
            need(total <= 5000000, 'Original maximum total steps')
            if pc < 0x80000000:
                need(not retired and len(boot) < 5 and (pc,insn) == boot_expected[len(boot)], 'Boot identity/order')
                boot.append((pc,insn))
                continue
            need(len(boot) == 5 and pc in codebook and int(codebook[pc]['insn'],16) == insn,
                 f'Actual ELF PC/code mismatch line{lineno}')
            all_pcs[pc] += 1
            if exited:
                need(pc == park['pc'] and insn == 0xa001 and not rest.strip(), 'Post-HTIF effects/nonparking')
                parking += 1
                continue
            retired += 1
            need(pc not in unused, 'Unused helper interior retired')
            need(not step or pc == routine[step]['pc'], 'Noncontiguous selected13 window')
            need(not capstep or pc == capacity[capstep]['pc'], 'Noncontiguous capacity window')
            rd = intreg.search(rest)
            accesses = [(int(a,16), int(b,16) if b else None) for a,b in mem.findall(rest)]
            if insn & 127 == 0x23:
                width = 1 << ((insn >> 12)&7)
                need(width <= 8 and len(accesses) == 1, 'Scalar store encoding/payload')
                a,v = accesses[0]
                need(v is not None, 'Store value missing')
                for b in range(width):
                    memory[a+b] = (v >> (8*b))&255
                if width == 1 and addresses['replay_log'] <= a < addresses['replay_log']+8192:
                    console[a-addresses['replay_log']] = v
            i = selected.get(pc)
            if pc in cap_lookup:
                ci = cap_lookup[pc]
                need(ci == capstep and not calls and caps == 0, 'Capacity ownership')
                capstep = (capstep+1)%len(capacity)
                if capstep == 0:
                    caps += 1
                if ci == 1:
                    need(rd and int(rd[1]) == 10 and int(rd[2],16) == 512, 'Capacity actual vset return')
            if pc in bootcsrs:
                csr_counts[pc] += 1
                need(csr_counts[pc] == 1 and not calls, 'Extra/late bootstrap CSR')
                if insn != 0x00805073:
                    need(rd and int(rd[2],16) == 128, 'Actual vlenb not128')
            is_vec = (insn&127) in (0x57,0x5b) or ((insn&127) in (0x07,0x27,0x2f) and ((insn>>12)&7) in (0,5,6,7))
            is_vcsr = insn&127 == 0x73 and ((insn>>12)&7) and (insn>>20) in (8,9,10,15,0xc20,0xc21,0xc22)
            need(not (is_vec or is_vcsr) or i is not None or pc in cap_lookup or pc in bootcsrs,
                 'Extra RVV/vector CSR outside original windows')
            if i is not None:
                need(i == step and caps == 1, 'Selected order/capacity')
                if i == 0:
                    finish()
                    j = len(calls)
                    need(j < 98, 'Extra selected call')
                    g = gold[j]
                    args = [addresses['input'],addresses['indices'],addresses['output']+2,g['vl'],512,
                            addresses['predicate'],0,g['vstart']]
                    need([regs.get(r) for r in range(10,18)] == args, 'Original arguments/history')
                    for name, values, width in [('input',data,2),('indices',indices,2),('indices16',indices,2),
                                               ('predicate',g['predicate'],1),('output',[91]*514,2)]:
                        for k, want in enumerate(values):
                            address = addresses[name]+width*k
                            need(all(address+b in memory for b in range(width)), 'Setup byte missing')
                            need(sum(memory[address+b]<<(8*b) for b in range(width)) == want, 'Source/setup '+name)
                    current = dict(ordinal=j+1, tuple=g['tuple'], vl=g['vl'], vstart=g['vstart'], reads=set())
                    calls.append(current)
                if i in (0,5,10):
                    need(rd and int(rd[1]) == 5 and int(rd[2],16) == (g['vl'] if i == 5 else 512), 'vset return')
                if i == 8:
                    need(insn == 0x5c880c57 and csr.get('vtype') == 11 and csr.get('vl') == g['vl'] and
                         csr.get('vstart') == g['vstart'], 'Actual merge target/CSR')
                    need(group(8) == data and group(16) == indices and group(24) == [91]*512, 'Actual inputs/oldvd')
                    need(vectors[0]&((1<<512)-1) == int.from_bytes(bytes(g['predicate'][:64]),'little'), 'Actual selector')
                    need(regs.get(16) == regs.get(28) == 0, 'Original scalar/move drift')
                    current.update(target_line=lineno,target_retired=retired,
                        selector_one=sum((g['predicate'][k//8]>>(k%8))&1 for k in range(g['vstart'],g['vl'])),
                        selector_zero=sum(1-((g['predicate'][k//8]>>(k%8))&1) for k in range(g['vstart'],g['vl'])))
                if i == 9:
                    need(rd and int(rd[1]) == 10 and int(rd[2],16) == 0, 'Returned vstart')
                    current['vstart_returned'] = 0
                if i == 11:
                    need(csr.get('vl') == 512 and group(24) == g['output'] and
                         accesses == [(addresses['output']+2+2*k,v) for k,v in enumerate(g['output'])], 'Full512 vector store')
                counts[i] += 1
                step = (step+1)%13
            for r,v in vec.findall(rest):
                vectors[int(r)] = int(v,16)
            for name,v in csrs.findall(rest):
                csr[name] = int(v,16)
            if i in (0,5,10):
                need(csr.get('vl') == (g['vl'] if i == 5 else 512) and csr.get('vtype') == 11, 'Actual vset state')
            if i == 8:
                need(group(24) == g['output'] and csr.get('vstart') == 0, 'Full merge result/vstart reset')
            if current is not None and insn&127 == 3:
                for address, value in accesses:
                    if addresses['output'] <= address < addresses['output']+1028:
                        need(step == 0 and (insn>>12)&7 == 5 and rd and value is None and
                             (address-addresses['output'])%2 == 0, 'Original scalar LHU oracle')
                        k = (address-addresses['output'])//2
                        need(k not in current['reads'] and int(rd[2],16) ==
                             (91 if k in (0,513) else g['output'][k-1]), 'Full output/guard mismatch')
                        current['reads'].add(k)
                        checks += 1
            if pc == store['pc']:
                need(accesses == [(addresses['tohost'],1)] and counts == [98]*13, 'Successful HTIF identity/count')
                finish()
                exited = True
            if rd:
                regs[int(rd[1])] = int(rd[2],16)
    after = raw_path.stat()
    need((before.st_size,before.st_mtime_ns,before.st_ino) == (after.st_size,after.st_mtime_ns,after.st_ino), 'Raw changed')
    need(exited and len(calls) == 98 and counts == [98]*13 and checks == 50372 and caps == 1, 'Full execution missing')
    need(all(csr_counts[p] == 1 for p in bootcsrs), 'Bootstrap CSR count')
    need(total == 2025000 and retired == 2020160 and parking == 4835 and total == retired+5+parking, 'Actual retirement accounting')
    need(after.st_size == 130671353 and digest.hexdigest() == rec['commit_sha256'], 'Full raw hash/size')
    for observed, recorded in zip(calls, rec['calls']):
        need(observed['tuple'] == recorded['original_tuple'] and
             observed['target_line'] == recorded['target']['trace_line'] and
             observed['target_retired'] == recorded['target']['retired'], 'Recorded targets differ')
    text = console.split(b'\0',1)[0].decode('ascii')
    need(text == rec['reconstructed_console'] == (PREP/'reference/runtime.log').read_text(), 'Reconstructed raw console')
    for marker in (f'BOARD_CASE_BEGIN {NAME}', 'RVV_MERGE_PREFIX_PASS sew=16 cases=98 errors=0',
                   f'BOARD_CASE_PASS {NAME}', 'BOARD_REPLAY_PASS'):
        need(text.splitlines().count(marker) == 1, 'Exact success markers')
    need(not re.search(r'FAIL|TRAP|MISMATCH|DETAIL|RVV_PERMUTE_PASS',text), 'Raw console veto')
    return dict(calls=calls, helper_counts=counts, fullcap_results=50176, guards=196, scalar_checks=checks,
                returned_vstart=98, vset_returns=294, full_input_vector_checks=98,
                full_result_vector_checks=98, full_vector_store_checks=98, capacity_calls=caps,
                unused_helper_retirements=0, other_rvv_retirements=0,
                bootstrap_csr_counts={hex(p):n for p,n in csr_counts.items()},
                selector_zero=sum(c['selector_zero'] for c in calls), selector_one=sum(c['selector_one'] for c in calls),
                firmware_retired=retired, boot=boot, post_htif_park=parking, raw_records=total,
                raw_bytes=after.st_size, raw_sha256=digest.hexdigest(), raw_full_passes=1,
                console=text, all_retired_pc_counts={hex(p):n for p,n in sorted(all_pcs.items())})


def main():
    need(sys.argv[1:] == ['--read-existing-once'], 'Explicit offline audit only')
    need(not (OUT/'attempt.json').exists(), 'Do not repeat existing audit')
    save('attempt.json', dict(status='OFFLINE_EXISTING_RAW_AUDIT_STARTED', script_sha256=sha(Path(__file__))))
    try:
        ready, proof, pins, code, functions, expected, asm = prepare()
        command, execution = read(PREP/'reference/command.json'), read(PREP/'reference/execution.json')
        need(command['command'] == execution['command'] and execution['returncode'] == 0 and
             execution['elapsed_s'] < 120 and command['max_steps'] == 5000000 and command['seconds'] == 120 and
             command['max_log_bytes'] == 805306368 and command['attempt'] == 1 and command['retry'] is False and
             '--isa=rv64gcv_zvl1024b' in command['command'] and command['command'][-1] == ready['spike_elf']['path'],
             'Original bounded reference execution/profile')
        result = parse(code, functions, expected)
        need(result['raw_sha256'] == pins[str(PREP/'reference/commits.log')], 'READY raw pin')
        for p,h in pins.items():
            if Path(p) != PREP/'reference/commits.log':
                need(sha(Path(p)) == h, 'Post-audit pin drift '+p)
        need(sha(PREP/'READY.json') == READY_SHA, 'READY changed during audit')
        save('audit.json', dict(status='ACCEPTED_SOURCE_REFERENCE_PREFIX98_ONLY_NOT_DUT', ready_sha256=READY_SHA,
             original_child=CHILD, soc_elf=ready['soc_elf'], spike_elf=ready['spike_elf'], source_asm=asm,
             pin_count=len(pins), pins=pins, evidence=result, reference_command=command,
             reference_execution=execution, original_stopped_tuple=None, historical_stall_closed=False,
             full_child_acceptance=False, dut_launch_authorized=False, auditor_sha256=sha(Path(__file__))))
        print('ACCEPTED_SOURCE_REFERENCE_PREFIX98_ONLY_NOT_DUT', result['firmware_retired'], result['raw_sha256'])
    except Exception as error:
        save('not_accepted.json', dict(status='NOT_ACCEPTED', error=repr(error), auditor_sha256=sha(Path(__file__))))
        raise


if __name__ == '__main__':
    main()
