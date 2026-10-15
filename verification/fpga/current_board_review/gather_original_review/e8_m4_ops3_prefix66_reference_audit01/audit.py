#!/usr/bin/env python3
"""One authorized offline m4/VI31 audit. No compiler or simulator invocation."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True
from model import (CHILD, RUNTIME, CAP, VLENB, CALLS, ELF_SHA, C_SHA, S_SHA,
                   PART, need, sha, independent_model, original_source_identity,
                   expected_prefix)

OUT = Path(__file__).resolve().parent
PREP = OUT.parent / 'e8_m4_ops3_prefix66_prepare01'
RAW = PREP / 'reference/commits.log'
ROOT = OUT.parents[4]
OBJ = ROOT / 'install/riscv-gcc/bin/riscv64-unknown-elf-objdump'
READY_SHA = '11aec353de588baa6981aa0e46757b76efdbcf7c0656585d5174e96aca523ebc'
OLD_SHA = 'f090f0d597b9e35a101a1f018a93ca9f61a04349c4243724f5c55e97094a7649'
PROOF_SHA = '7cc7582e71120bce71e5c29de897c271330ce0fa7a5c32dd6dad97dfb5c9cddd'


def read(p):
    return json.loads(Path(p).read_text())


def save(p, value):
    with Path(p).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def merge_pins(*tables):
    pins = {}
    for table in tables:
        for p, h in table.items():
            need(p not in pins or pins[p] == h, 'Conflicting pin: '+p)
            pins[p] = h
    return pins


def verify(pins):
    for p, h in pins.items():
        if Path(p) != RAW:
            need(sha(p) == h, 'Pin drift: '+p)


def stat_identity(p):
    s = p.stat()
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def disassemble(elf):
    text = subprocess.check_output([str(OBJ), '-d', str(elf)], text=True, timeout=20)
    rows = []
    for line in text.splitlines():
        m = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+(.+)', line)
        if m:
            rows.append(dict(pc=int(m[1], 16), insn=m[2], text=m[3]))
    raw = Path(elf).read_bytes()
    need(raw[:6] == b'\x7fELF\x02\x01', 'ELF64 little endian')
    phoff = struct.unpack_from('<Q', raw, 32)[0]
    phsize, phnum = struct.unpack_from('<HH', raw, 54)
    loads = []
    for i in range(phnum):
        p = struct.unpack_from('<IIQQQQQQ', raw, phoff+i*phsize)
        if p[0] == 1:
            loads.append((p[3], p[3]+p[5], p[2]))
    for row in rows:
        pc, width = row['pc'], len(row['insn'])//2
        match = [(lo, off) for lo, hi, off in loads if lo <= pc and pc+width <= hi]
        need(len(match) == 1, 'Unique executable instruction bytes')
        lo, off = match[0]
        need(int.from_bytes(raw[off+pc-lo:off+pc-lo+width], 'little') == int(row['insn'], 16),
             'Disassembly differs from ELF bytes')
    syms = {}
    symbols = subprocess.check_output([str(OBJ), '-t', str(elf)], text=True, timeout=20)
    for line in symbols.splitlines():
        fields = line.split()
        if len(fields) >= 5 and re.fullmatch('[0-9a-f]+', fields[0]):
            syms[fields[-1]] = (int(fields[0], 16), int(fields[-2], 16))
    return rows, syms


def slice_at(rows, pc, count):
    hits = [i for i, r in enumerate(rows) if r['pc'] == pc]
    need(len(hits) == 1, 'Unique routine entry')
    return rows[hits[0]:hits[0]+count]


def adapted_source(source):
    value = ('/* Architectural port of '+RUNTIME+'; original identity in provenance.json.\n'
             ' * Not an original Linux ELF replay or a fault/restart OS test. */\n'+source)
    begin = value.index('static long syscall3(')
    end = value.index('\nstatic void text', begin)
    value = value[:begin]+'extern long replay_write(long, long, long, long);\n#define syscall3 replay_write'+value[end:]
    changes = {
        'void probe_main(void){': 'int '+RUNTIME+'_main(void) {',
        'syscall3(94,2,0,0);for(;;){}': 'return 2;',
        'syscall3(29,1,0x5409,1);': '/* Linux TIOCOUTQ omitted; timing is not equivalent. */',
        'syscall3(94,errors ? 1:0,0,0);for(;;){}': 'return errors ? 1 : 0;',
    }
    for old, new in changes.items():
        need(value.count(old) == 1, 'Unique adaptation: '+old)
        value = value.replace(old, new)
    start = value.index('__asm__(".global _start')
    return value[:start]


def preflight():
    need(sha(PREP/'READY02.json') == READY_SHA and sha(PREP/'READY.json') == OLD_SHA, 'Exact readiness')
    ready, old = read(PREP/'READY02.json'), read(PREP/'READY.json')
    proof_path = PREP/'original_linux_rebuild02/proof.json'
    need(sha(proof_path) == PROOF_SHA == ready['full_linux_rebuild_proof_sha256'], 'Exact supplement')
    proof = read(proof_path)
    need(proof['status'] == 'PASS_FULL_ORIGINAL_LINUX_ELF_BYTE_IDENTICAL' and
         proof['actual_numeric_returncode'] == 0 and proof['compile_attempts'] == 1 and
         ready['entire_original_linux_binary_rebuild_proven'] is True, 'Actual original rebuild')
    need(sha(proof['original_linux_elf']) == sha(proof['rebuilt_linux_elf']) == ELF_SHA and
         Path(proof['original_linux_elf']).read_bytes() == Path(proof['rebuilt_linux_elf']).read_bytes(),
         'Entire original rebuilt binary differs')
    for k in ('soc_elf', 'spike_elf', 'reference_sha256', 'source_proof_sha256', 'ordered_tuples'):
        need(ready[k] == old[k], 'Supplement changed prior source/reference: '+k)
    need(all(ready['pins'].get(p) == h for p, h in old['pins'].items()), 'Old pin not retained')
    freeze = (PREP/'REBUILD02_RESULT.md').read_text()
    need('All readiness-bound inputs are now frozen; no further edits or runs.' in freeze,
         'Producer final freeze confirmation absent')
    original = original_source_identity()
    pins = merge_pins(ready['pins'], old['pins'], proof['pins'], read(PREP/'baseline_pins.json'),
                      read(PREP/'original_linux_rebuild02/input_pins.json'), original['pins'],
                      {str(PREP/'READY02.json'): READY_SHA, str(PREP/'READY.json'): OLD_SHA})
    verify(pins)
    gold = independent_model()
    need(ready['ordered_tuples'] == [g['tuple'] for g in gold['rows']], 'Natural order')
    for k, v in dict(source_label=CHILD, runtime_id=RUNTIME, sew=8, lmul='m4',
                     capacity=512, vlenb=128, calls=66, predecessors=65,
                     physical_predicate_bytes=128, fullcap_results=33792, guards=132,
                     helper_instruction_count=858, setup_values_per_call=2178,
                     setup_bytes_per_call=2690).items():
        need(ready[k] == v, 'Scope differs: '+k)
    recorded_model = read(PREP/'host_expected.json')
    for k in ('input', 'indices', 'indices16', 'rows'):
        need(recorded_model[k] == gold[k], 'Independent original model differs: '+k)
    directory = PREP/'prepared'/RUNTIME
    src = (directory/'original/scenario.c').read_text()
    need(sha(directory/'original/scenario.c') == C_SHA, 'Copied original C')
    adapter = adapted_source(src)
    port = expected_prefix(adapter)
    need(port == (directory/'case.c').read_text(), 'Adapter/prefix changed original oracle')
    for name, before, after in [('adapter', src, adapter), ('prefix', adapter, port)]:
        diff = ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                    fromfile=name+'_before', tofile=name+'_after'))
        need(diff == (PREP/'source_diffs'/f'{name}.diff').read_text(), 'Recorded source diff')
    prov = read(PREP/'prepared/provenance.json')
    case, = prov['cases']
    need(case['id'] == RUNTIME and case['source_label'] == CHILD and case['operation'] == 3 and
         case['original_case'] == original['case'] and
         case['defines'] == ['SEW=8', 'RESTART_PERMUTATIONS=1', 'PERMUTE_OP_MASK=8'], 'Manifest/runtime mapping')
    for p, h in prov['files'].items():
        need(sha(PREP/'prepared'/p) == h, 'Prepared manifest checksum')
    sp = read(PREP/'source_elf_proof.json')
    need(sha(PREP/'source_elf_proof.json') == ready['source_proof_sha256'], 'Source proof')
    codes = [r['insn'] for r in sp['original_routine']]
    need(len(codes) == 13 and codes[8] == '308fbc57', 'Original target encoding')
    machine = {}
    for kind, elf in [('original', Path(proof['original_linux_elf'])),
                      ('soc', Path(ready['soc_elf']['path'])), ('spike', Path(ready['spike_elf']['path']))]:
        rows, symbols = disassemble(elf)
        rr = slice_at(rows, sp[kind+'_routine'][0]['pc'], 13)
        need(rr == sp[kind+'_routine'] and [r['insn'] for r in rr] == codes, 'Actual13 helper '+kind)
        if kind != 'original':
            need(read(PREP/(kind+'01')/'programs.json')['programs'][RUNTIME] == ready[kind+'_elf'],
                 'ELF program manifest')
            need(symbols['predicate'][1] == 128 and symbols['output'][1] == 1026 and
                 symbols['input'][1] == symbols['indices'][1] == 1024, 'Actual physical array dimensions')
        machine[kind] = (rows, symbols)
    rows, syms = machine['spike']
    cap = slice_at(rows, syms[RUNTIME+'_capacity'][0], 3)
    need([r['insn'] for r in cap] == ['52fd', '0022f557', '8082'], 'Capacity512 helper')
    exits = slice_at(rows, syms['replay_exit'][0], 7)
    need(exits[-2]['insn'] == '00a2b023' and exits[-1]['insn'] == 'a001' and
         exits[-1]['text'].startswith('j\t'+format(exits[-1]['pc'], 'x')), 'Original exit/park')
    unused = []
    for op in range(21):
        rr = slice_at(rows, syms[RUNTIME+'_op_'+str(op)][0], 13)
        if op != 3:
            unused.append((rr[0]['pc'], rr[-1]['pc']+len(rr[-1]['insn'])//2))
    execution = read(PREP/'reference/execution.json')
    command = read(PREP/'reference/command.json')
    need(type(execution['returncode']) is int and execution['returncode'] == 0 and
         execution['retries'] == 0 and execution['spike_launches'] == 1 and
         0 < execution['elapsed_s'] < 120 and execution['command'] == command['command'], 'Reference actual exit')
    need(command['instructions'] == 3000000 and command['seconds'] == 120 and
         command['file_bytes'] == 768*1024*1024 and '--isa=rv64gcv_zvl1024b' in command['command'] and
         command['command'][-1] == ready['spike_elf']['path'], 'Exact reference budget/profile')
    need((PREP/'reference/spike.cmd').read_text() == f'rs 3000000\nstr {syms["replay_log"][0]:x}\nquit\n',
         'Actual debug instruction bound')
    return ready, pins, gold, sp, machine['spike'], cap, exits, unused


HEADER = re.compile(r'core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)')
INTEGER = re.compile(r'\bx(\d+)\s+0x([0-9a-f]+)')
VECTOR = re.compile(r'\bv(\d+)\s+0x([0-9a-f]+)')
CSR = re.compile(r'\bc\d+_(\w+)\s+0x([0-9a-f]+)')
MEM = re.compile(r'\bmem\s+0x([0-9a-f]+)(?:\s+0x([0-9a-f]+))?')
TOKENS = re.compile(r'\s+(?:[xfv]\d+\s+0x[0-9a-f]+|c\d+_\w+\s+0x[0-9a-f]+|'
                    r'mem\s+0x[0-9a-f]+(?:\s+0x[0-9a-f]+)?|e\d+\s+mf?\d+\s+l\d+)')


def parse_once(ready, pins, gold, proof, machine, capacity, exits, unused):
    rows, symbols = machine
    code_map = {r['pc']: int(r['insn'], 16) for r in rows}
    routine = proof['spike_routine']
    lookup = {r['pc']: i for i, r in enumerate(routine)}
    addresses = {n: symbols[n][0] for n in ('input', 'indices', 'indices16', 'predicate', 'output', 'replay_log', 'tohost')}
    boot = [(0x1000, 0x297), (0x1004, 0x02028593), (0x1008, 0xf1402573),
            (0x100c, 0x0182b283), (0x1010, 0x28067)]
    regs, memory, vectors, csrs = {0: 0}, {}, {}, {}
    calls, counts, loads, retired, parks, vlenb = [], [0]*13, 0, 0, 0, []
    cap_count, boot_count, step, current, exited = 0, 0, 0, None, False
    console = bytearray(8192)
    digest = hashlib.sha256()
    before = stat_identity(RAW)
    need(before[2] == ready['actual_reference_raw_bytes'] < 768*1024*1024, 'Raw size/bound')
    save(OUT/'parse_started.json', dict(raw=str(RAW), stat=before, single_attempt=True,
        ready_sha256=READY_SHA, auditor_sha256=sha(__file__), time=time.time()))

    def group(first):
        need(all(n in vectors for n in range(first, first+4)), 'Missing actual m4 register')
        return list(b''.join(vectors[n].to_bytes(128, 'little') for n in range(first, first+4)))

    def finish():
        if current is not None:
            need(step == 0 and current['reads'] == set(range(514)), 'Missing full scalar oracle/guards')
            need(current.get('returned_vstart') == 0, 'Missing returned vstart')
            current.pop('reads')

    with RAW.open('rb') as stream:
        for lineno, raw in enumerate(stream, 1):
            digest.update(raw)
            need(lineno <= 3000000, 'Total raw record budget')
            line = raw.decode('ascii').rstrip('\n')
            m = HEADER.fullmatch(line)
            need(m is not None and 'trap_' not in line, f'Unknown/trap raw record line{lineno}')
            privilege, pc, code, rest = int(m[1]), int(m[2], 16), int(m[3], 16), m[4]
            need(not TOKENS.sub('', rest).strip(), f'Unknown raw payload line{lineno}')
            if exited:
                need(privilege == 3 and pc == exits[-1]['pc'] and code == 0xa001 and not rest.strip(),
                     'Post-exit side effect/nonoriginal park')
                parks += 1
                continue
            if pc < 0x80000000:
                need(retired == 0 and boot_count < 5 and (pc, code) == boot[boot_count] and privilege == 3,
                     'Exact boot record/order')
                boot_count += 1
                continue
            need(boot_count == 5 and privilege == 3 and code_map.get(pc) == code, 'Actual ELF PC/code/mode')
            need(not any(lo <= pc < hi for lo, hi in unused), 'Unused helper range executed')
            need(pc != symbols['trap_entry'][0], 'Default trap executed')
            retired += 1
            rd = INTEGER.search(rest)
            accesses = [(int(a,16), int(v,16) if v else None) for a,v in MEM.findall(rest)]
            i = lookup.get(pc)
            if step:
                need(i == step, 'Interrupted thirteen-instruction window')
            op = code & 127
            rvv = op == 87 or op in (7,39) and (code >> 12)&7 in (0,5,6,7)
            if rvv:
                need(i is not None or pc == capacity[1]['pc'], 'Vector instruction outside exact windows')
            if op == 115 and code >> 20 == 0xc22:
                need(rd and int(rd[2],16) == 128 and not calls, 'Actual vlenb128 startup')
                vlenb.append(dict(pc=hex(pc), line=lineno, value=128))
            if pc == capacity[1]['pc']:
                need(not calls and cap_count == 0 and code == 0x0022f557 and rd and
                     (int(rd[1]), int(rd[2],16)) == (10,512), 'Actual original VLMAX512')
                cap_count += 1
            # Scalar writes reconstruct initialization; vector output is audited directly below.
            if op == 35:
                width = 1 << ((code >> 12)&7)
            elif code & 3 != 3 and (code >> 13)&7 in (6,7):
                width = 4 if (code >> 13)&7 == 6 else 8
            else:
                width = 0
            if width:
                need(width <= 8, 'Scalar store width')
                for addr, val in accesses:
                    need(val is not None, 'Scalar write missing value')
                    for b in range(width):
                        memory[addr+b] = (val >> (8*b))&255
                    if width == 1 and addresses['replay_log'] <= addr < addresses['replay_log']+8192:
                        console[addr-addresses['replay_log']] = val&255
            if i is not None:
                need(i == step, 'Helper order')
                if i == 0:
                    finish()
                    need(len(calls) < 66 and cap_count == 1, 'Extra/early helper')
                    g = gold['rows'][len(calls)]
                    args = [addresses['input'], addresses['indices'], addresses['output']+1,
                            g['vl'], 512, addresses['predicate'], 0, g['vstart']]
                    need([regs.get(n) for n in range(10,18)] == args, 'Original eight arguments')
                    for name, values, size in [('input',gold['input'],1), ('indices',gold['indices'],1),
                        ('indices16',gold['indices16'],2), ('predicate',g['predicate'],1), ('output',[91]*514,1)]:
                        for k, want in enumerate(values):
                            at = addresses[name]+size*k
                            need(all(at+b in memory for b in range(size)), 'Missing setup bytes '+name)
                            got = sum(memory[at+b] << (8*b) for b in range(size))
                            need(got == want, f'Independent setup {name}[{k}]')
                    current = dict(ordinal=len(calls)+1, tuple=g['tuple'], vl=g['vl'],
                                   vstart=g['vstart'], reads=set())
                    calls.append(current)
                if i in (0,5,10):
                    need(rd and (int(rd[1]), int(rd[2],16)) == (5,g['vl'] if i == 5 else 512), 'vset return')
                if i == 8:
                    need(code == 0x308fbc57 and csrs.get('vl') == g['vl'] and
                         csrs.get('vstart') == g['vstart'] and csrs.get('vtype') == 2, 'VI31 target CSR')
                    need(group(8) == gold['input'] and group(16) == gold['indices'] and group(24) == [91]*512,
                         'Actual complete m4 source/old destination')
                    need(0 in vectors and vectors[0]&((1<<512)-1) == int.from_bytes(bytes(g['predicate'][:64]),'little'),
                         'Actual consumed predicate')
                    need(regs.get(28) == regs.get(16) == 0 and regs.get(17) == g['vstart'], 'Original scalar/start')
                    current.update(target_pc=hex(pc), opcode=hex(code), target_line=lineno,
                                   target_retired=retired, actual_source31=group(8)[31])
                if i == 9:
                    need(rd and (int(rd[1]),int(rd[2],16)) == (10,0), 'Returned vstart0')
                    current['returned_vstart'] = 0
                if i == 11:
                    need(csrs.get('vl') == 512 and group(24) == g['output'], 'Full result at vector store')
                    need(accesses == [(addresses['output']+1+k,v) for k,v in enumerate(g['output'])],
                         'Full512 ordered vector stores')
                counts[i] += 1
                step = (step+1)%13
            for n,v in VECTOR.findall(rest):
                vectors[int(n)] = int(v,16)
            for n,v in CSR.findall(rest):
                csrs[n] = int(v,16)
            if pc == capacity[1]['pc']:
                need(csrs.get('vl') == 512 and csrs.get('vtype') == 2, 'Capacity state')
            if i in (0,5,10):
                need(csrs.get('vl') == (g['vl'] if i == 5 else 512) and csrs.get('vtype') == 2, 'Actual vset state')
            if i == 8:
                need(group(24) == g['output'] and csrs.get('vstart') == 0, 'Full target result/reset')
            if current is not None and op == 3:
                for addr,val in accesses:
                    if addresses['output'] <= addr < addresses['output']+514:
                        need(step == 0 and (code >> 12)&7 == 4 and rd and val is None, 'Actual scalar LBU oracle')
                        index = addr-addresses['output']
                        need(index not in current['reads'], 'Duplicate oracle load')
                        want = 91 if index in (0,513) else g['output'][index-1]
                        need(int(rd[2],16) == want, 'Full result/guard differs')
                        current['reads'].add(index)
                        loads += 1
            if pc == exits[-2]['pc'] or any(a == addresses['tohost'] for a,v in accesses):
                need(pc == exits[-2]['pc'] and code == 0x00a2b023 and accesses == [(addresses['tohost'],1)],
                     'Exact successful HTIF exit')
                finish()
                exited = True
            if rd:
                regs[int(rd[1])] = int(rd[2],16)
            regs[0] = 0
    need(stat_identity(RAW) == before, 'Raw changed during traversal')
    need(digest.hexdigest() == pins[str(RAW)], 'Raw hash differs')
    need(exited and len(calls) == 66 and counts == [66]*13 and loads == 33924 and
         len(vlenb) == 2 and cap_count == 1, 'Incomplete actual scope')
    recorded = read(PREP/'reference/reference.json')
    need(retired == ready['actual_firmware_retired'] == recorded['firmware_retired_to_htif_store'], 'Reference retirement metadata')
    for c, r in zip(calls, recorded['calls']):
        need(c['tuple'] == r['original_tuple'] and c['target_line'] == r['target']['trace_line'] and
             c['target_retired'] == r['target']['retired'] and c['actual_source31'] == r['actual_source31'] == 177,
             'Stored target evidence differs')
    console_text = console.split(b'\0',1)[0].decode('ascii')
    need(console_text == recorded['reconstructed_console'] == (PREP/'reference/runtime.log').read_text(), 'Raw console differs')
    for marker in ready['spike_elf']['pass_markers']:
        need(console_text.splitlines().count(marker) == 1, 'Exact console marker')
    need(not re.search(r'FAIL|TRAP|MISMATCH|DETAIL|RVV_PERMUTE_PASS', console_text), 'Raw error veto')
    return dict(calls=calls, helper_counts=counts, full_results=33792, guards=132,
                scalar_loads=loads, full_vector_inputs_results_stores=66, vlenb_reads=vlenb,
                capacity_returns=cap_count, firmware_retired=retired, boot_records=boot_count,
                post_exit_original_park_records=parks, total_raw_records=lineno,
                raw_sha256=digest.hexdigest(), raw_bytes=before[2], raw_stat=before,
                reconstructed_console=console_text, physical_predicate_bytes=128,
                logical_predicate_bytes=64, endpoint=gold['endpoint'], actual_source31=177)


def main():
    need(sys.argv[1:] == ['--authorized-once'], 'Explicit one-audit invocation required')
    start = time.monotonic()
    def expired(*_):
        raise TimeoutError('Independent audit exceeded590s inner bound')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(590)
    save(OUT/'invocation_started.json', dict(pid=os.getpid(), started=time.time(),
        ready_sha256=READY_SHA, max_seconds=600, no_retry=True))
    try:
        audit_pins = read(OUT/'auditor_pins.json')
        verify(audit_pins)
        ready, pins, gold, proof, machine, cap, exits, unused = preflight()
        save(OUT/'verified_input_pins.json', pins)
        result = parse_once(ready, pins, gold, proof, machine, cap, exits, unused)
        verify(pins)
        verify(audit_pins)
        need(stat_identity(RAW) == result['raw_stat'], 'Raw changed after traversal')
        result.update(status='ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT', ready_sha256=READY_SHA,
                      old_ready_sha256=OLD_SHA, full_original_binary_proof_sha256=PROOF_SHA,
                      pins_pre_post_unchanged=True, input_pin_count=len(pins), raw_parses=1,
                      auditor_sha256=sha(__file__), model_sha256=sha(OUT/'model.py'),
                      elapsed_s=time.monotonic()-start, numeric_prefix66_only=True,
                      unknown_stall_reproduction=False, full2688_execution=False, DUT=False)
        save(OUT/'audit.json', result)
        print(result['status'], 'retired', result['firmware_retired'], 'seconds', result['elapsed_s'], flush=True)
    except BaseException as error:
        save(OUT/'failure.json', dict(status='INDEPENDENT_AUDIT_NOT_PASS', error=repr(error),
                                    elapsed_s=time.monotonic()-start, no_auto_retry=True))
        raise
    finally:
        signal.alarm(0)


if __name__ == '__main__':
    main()
