#!/usr/bin/env python3
"""Independent PC-only terminal supplement. Never launch or alter the worker."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
GATHER = HERE.parent
ROOT = HERE.parents[4]
NAME = 'gather_prefix_e8_m8_ops2'
PLAN = GATHER / 'e8_m8_ops2_prefix112_vcs_m6_plan01/prepared01/plan.json'
PLAN_SHA = 'bb3b5302ce2c65ec91874c22ed85705488aae4ba2043ad32b285ba60c6d81c11'
PREP = GATHER / 'e8_m8_ops2_prefix112_prepare01'
ELF_SHA = 'a0445bcb877799d488e40f37d7bcbc038d9f0e36a7a60e147ed8baf3c5ea5f74'
WORKER_PASS = 'PASS_M6_ORIGINAL_E8M8_VI0_PREFIX112_NOT_FULL_CHILD'
EVENTS = {'retire', 'cvx_req', 'cvx_resp', 'arch_start', 'uop_alloc', 'uop_done'}
FIELDS = {'cycle', 'event', 'order', 'pc', 'insn', 'trap', 'rd', 'rd_wdata', 'mem_addr',
          'mem_rmask', 'mem_wmask', 'mem_wdata'}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def vector_instruction(insn):
    # Match the pinned CVX classifier, including vector CSRs and custom offloads.
    opcode, funct3 = insn & 127, (insn >> 12) & 7
    if opcode in (0x57, 0x5b):
        return True
    if opcode in (0x07, 0x27, 0x2f):
        return funct3 in (0, 5, 6, 7)
    return opcode == 0x73 and funct3 != 0 and insn >> 20 in (
        0x008, 0x009, 0x00a, 0x00f, 0xc20, 0xc21, 0xc22)


def elf_text(path):
    raw = path.read_bytes()
    require(raw[:6] == b'\x7fELF\x02\x01', 'Not ELF64 little endian')
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    require(header[2] == 243, 'Not RISC-V ELF')
    shoff, shsize, shnum, shstr = header[6], header[11], header[12], header[13]
    sections = [struct.unpack_from('<IIQQQQIIQQ', raw, shoff+i*shsize) for i in range(shnum)]
    strings = sections[shstr]
    names = raw[strings[4]:strings[4]+strings[5]]
    text, = [s for s in sections if names[s[0]:].split(b'\0', 1)[0] == b'.text']
    require(text[2] & 4, 'Text is not executable')
    return text[3], raw[text[4]:text[4]+text[5]]


def specification():
    require(sha(PLAN) == PLAN_SHA, 'Sealed plan drift')
    plan = read(PLAN)
    proof_path = PREP / 'source_elf_proof.json'
    asm_path = PREP / 'prepared' / NAME / 'original/operations.S'
    elf = Path(plan['case']['elf'])
    objdump = ROOT / 'install/riscv-gcc/bin/riscv64-unknown-elf-objdump'
    paths = [proof_path, asm_path, elf, objdump,
             PREP/'prepared'/NAME/'case.c', PREP/'prepared/startup.S',
             PREP/'prepared/runtime.c', PREP/'soc01'/f'{NAME}_main.c', PLAN.parents[1]/'checker.py',
             PLAN.parents[1]/'replay.py']
    pins = {str(PLAN): PLAN_SHA}
    for path in paths:
        digest = sha(path)
        require(digest == plan['pins'].get(str(path)), 'Input pin drift: '+str(path))
        pins[str(path)] = digest
    require(sha(elf) == ELF_SHA == plan['case']['sha256'], 'ELF identity')
    proof = read(proof_path)
    require(proof['soc_elf']['sha256'] == ELF_SHA, 'Source proof ELF differs')
    disassembly = subprocess.check_output([str(objdump), '-d', '-z', str(elf)], text=True)
    instructions, labels = {}, {}
    for line in disassembly.splitlines():
        match = re.fullmatch(r'([0-9a-f]+) <([^>]+)>:', line)
        if match:
            labels[match[2]] = int(match[1], 16)
        match = re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4}(?:[0-9a-f]{4})?)\s+(.+)$', line)
        if match:
            pc = int(match[1], 16)
            require(pc not in instructions, 'Duplicate disassembled PC')
            instructions[pc] = dict(pc=pc, insn=match[2], text=match[3].split('#')[0].strip())
    origin, raw = elf_text(elf)
    end, cursor = origin+len(raw), origin
    for pc, instr in sorted(instructions.items()):
        require(pc == cursor, 'Unclassified text byte/boundary at '+hex(cursor))
        code = bytes.fromhex(instr['insn'])[::-1]
        require(raw[pc-origin:pc-origin+len(code)] == code, 'Disassembly/ELF encoding differs')
        cursor += len(code)
    require(cursor == end, 'Unclassified trailing executable bytes')

    source_functions = {}
    current = None
    for line in asm_path.read_text().splitlines():
        line = line.strip()
        if line.endswith(':'):
            current = line[:-1]
            source_functions[current] = []
        elif line and not line.startswith('.'):
            require(current is not None, 'ASM instruction outside source function')
            source_functions[current].append(line)
    names = {k for k in labels if k.startswith(NAME+'_op_')}
    require(names == {NAME+'_'+k for k in source_functions if k.startswith('op_')},
            'ELF/source helper membership differs')
    starts = sorted(set(labels.values()) | {end})

    def function(name):
        start = labels[name]
        stop = next(p for p in starts if p > start)
        return [instructions[p] for p in sorted(instructions) if start <= p < stop]

    helpers = {name: function(name) for name in sorted(names)}
    capacity = function(NAME+'_capacity')
    compact = lambda s: re.sub(r'\s+', '', s)
    for name, routine in [*helpers.items(), (NAME+'_capacity', capacity)]:
        original = source_functions[name[len(NAME)+1:]]
        require([compact(r['text']) for r in routine] == [compact(s) for s in original],
                'Actual function/original ASM differs: '+name)
    routine = helpers[NAME+'_op_2']
    require(routine == proof['soc_routine'] == plan['spec']['routine'], 'Selected13 proof differs')
    require(len(routine) == 13 and [r['insn'] for r in routine] ==
            [r['insn'] for r in proof['original_routine']], 'Original13 code differs')
    require(routine[8]['insn'] == '30803c57', 'Not original VI0 target')
    require(len(capacity) == 3 and capacity[1]['insn'] == '0032f557', 'Capacity function changed')
    require(sum(vector_instruction(int(r['insn'], 16)) for r in routine) == 11, 'Selected CVX count')
    allowed = {r['pc'] for r in routine+capacity if vector_instruction(int(r['insn'], 16))}
    unused = {r['pc'] for n, rs in helpers.items() if n != NAME+'_op_2' for r in rs}
    wrapper_source = (PREP/'soc01'/f'{NAME}_main.c').read_text()
    require(wrapper_source.count('__asm__ volatile("csrr %0,vlenb"') == 1,
            'Wrapper vlenb source differs')
    vlenb, = [r for r in function('main') if r['insn'] == 'c2202773']
    max_start, = [r for r in function(NAME+'_main') if r['insn'] == 'c22027f3']
    startup, = [r for r in function('_start') if r['insn'] == '00805073']
    require((PREP/'prepared/startup.S').read_text().count('csrwi vstart, 0') == 1 and
            (PREP/'prepared'/NAME/'case.c').read_text().count('__asm__ volatile("csrr %0,vlenb"') == 1,
            'Original startup/max_start CSR source differs')
    bootstrap = [dict(startup, rd=0, value=0, prior_capacity=0),
                 dict(vlenb, rd=14, value=128, prior_capacity=0),
                 dict(max_start, rd=15, value=128, prior_capacity=1)]
    other_vector = {p for p, r in instructions.items() if vector_instruction(int(r['insn'], 16))}-allowed
    require(other_vector == unused.intersection(other_vector) | {r['pc'] for r in bootstrap},
            'Unexplained RVV outside original helpers/bootstrap CSRs')
    traps = {r['pc'] for name in ('trap_entry', 'replay_trap') for r in function(name)}
    exit_store, park = plan['spec']['exit_store'], plan['spec']['park']
    require(instructions[exit_store['pc']] == exit_store and instructions[park['pc']] == park,
            'SoC exit/park differs')
    windows = {name: dict(start=rs[0]['pc'], end=rs[-1]['pc']+len(rs[-1]['insn'])//2,
                         instruction_pcs=[r['pc'] for r in rs],
                         expected_each=112 if name == NAME+'_op_2' else 0)
               for name, rs in helpers.items()}
    return dict(instructions=instructions, helpers=helpers, helper_windows=windows, capacity=capacity,
                routine=routine, trap_pcs=sorted(traps), exit_store=exit_store, park=park,
                source_pins=pins, disassembly_sha256=hashlib.sha256(disassembly.encode()).hexdigest(),
                bootstrap=bootstrap, text_start=origin, text_end=end, expected_calls=112,
                expected_vector_retired=1236)


def audit_rows(rows, spec):
    insns = spec['instructions']
    selected, capacity = spec['routine'], spec['capacity']
    seq = {'op2': [r['pc'] for r in selected], 'capacity': [r['pc'] for r in capacity]}
    owners = {r['pc']: ('op2' if name == NAME+'_op_2' else name)
              for name, rs in spec['helpers'].items() for r in rs}
    owners.update({p: 'capacity' for p in seq['capacity']})
    trap_pcs = set(spec['trap_pcs'])
    counts, helper_counts = Counter(), Counter()
    total = retired = calls = cap_calls = vectors = parked = bootstrap_reads = 0
    bootstrap_pcs = {r['pc'] for r in spec['bootstrap']}
    last_cycle, active, step, exited = -1, None, 0, False
    for line, row in enumerate(rows, 2):
        total += 1
        require(FIELDS <= row.keys() and None not in row and all(row[k] is not None for k in FIELDS),
                f'Malformed CSV row {line}')
        event, cycle = row['event'], int(row['cycle'])
        require(event in EVENTS and cycle >= last_cycle, f'Event/cycle violation row {line}')
        last_cycle = cycle
        require(int(row['trap'] or '0') == 0, f'Trap/exception row {line}')
        if event != 'retire':
            continue
        require(int(row['order']) == retired, f'Retirement order row {line}')
        retired += 1
        pc, code = int(row['pc'], 16), int(row['insn'], 16)
        require(pc in insns, f'Unknown/non-boundary PC {pc:#x} row {line}')
        require(code == int(insns[pc]['insn'], 16), f'ELF encoding mismatch PC {pc:#x} row {line}')
        require(pc not in trap_pcs, f'Forbidden trap path PC {pc:#x} row {line}')
        require(insns[pc]['text'] != 'unimp' and not insns[pc]['text'].startswith('.'),
                f'Padding/illegal instruction PC {pc:#x} row {line}')
        counts[pc] += 1
        if exited:
            require(pc == spec['park']['pc'] and int(row['rd']) == 0 and
                    int(row['mem_rmask'], 16) == int(row['mem_wmask'], 16) == 0,
                    f'Post-exit non-park/side effect row {line}')
            parked += 1
            continue
        owner = owners.get(pc)
        if owner not in (None, 'op2', 'capacity'):
            raise ValueError(f'Unused helper {owner} PC {pc:#x} row {line}')
        if active:
            require(owner == active and pc == seq[active][step],
                    f'Noncontiguous/duplicate helper window PC {pc:#x} row {line}')
        elif owner:
            require(pc == seq[owner][0], f'Interior entry PC {pc:#x} row {line}')
            require((owner == 'capacity' and bootstrap_reads == 2 and cap_calls == calls == 0) or
                    (owner == 'op2' and bootstrap_reads == 3 and cap_calls == 1 and calls < 112),
                    f'Capacity/call count or order row {line}')
            active, step = owner, 0
        if owner:
            helper_counts[pc] += 1
            step += 1
            if step == len(seq[active]):
                if active == 'op2':
                    calls += 1
                else:
                    cap_calls += 1
                active, step = None, 0
        if vector_instruction(code):
            if pc in bootstrap_pcs:
                require(bootstrap_reads < 3, 'Extra bootstrap CSR')
                expected = spec['bootstrap'][bootstrap_reads]
                require(pc == expected['pc'] and calls == 0 and cap_calls == expected['prior_capacity'] and
                        int(row['rd']) == expected['rd'] and
                        (expected['rd'] == 0 or int(row['rd_wdata'], 16) == expected['value']),
                        'Extra/late/wrong bootstrap CSR')
                bootstrap_reads += 1
            else:
                require(owner in ('op2', 'capacity'), f'Unexpected RVV/CSR PC {pc:#x} row {line}')
            vectors += 1
        if pc == spec['exit_store']['pc'] or (int(row['mem_wmask'], 16) and int(row['mem_addr'], 16) == 0xd0000000):
            require(pc == spec['exit_store']['pc'] and int(row['mem_addr'], 16) == 0xd0000000 and
                    int(row['mem_wmask'], 16) == 255 and int(row['mem_wdata'], 16) == 0,
                    f'Wrong CTRL exit row {line}')
            require(active is None and calls == 112 and cap_calls == 1, 'Premature exit')
            exited = True
    require(exited and active is None and calls == 112 and cap_calls == 1, 'Incomplete helper/capacity/exit')
    require([helper_counts[p] for p in seq['op2']] == [112]*13, 'Selected instruction counts')
    require([helper_counts[p] for p in seq['capacity']] == [1]*3 and
            vectors == 1236 and bootstrap_reads == 3, 'Capacity/RVV counts')
    return dict(status='PASS_PC_SCOPE_ONLY_NOT_DATA_ORACLE', calls=calls, helper_counts=[112]*13,
                capacity_instruction_counts=[1]*3, capacity_vector_retired=1,
                bootstrap_csr_counts=[1]*3, vector_csr_retired=vectors,
                unused_helper_retired=0, other_vector_retired=0,
                rows=total, retired_rows=retired, last_cycle=last_cycle, parked=parked,
                all_helper_pc_counts={name: {hex(r['pc']): counts[r['pc']] for r in rs}
                                      for name, rs in spec['helpers'].items()},
                pc_counts={hex(p): n for p, n in sorted(counts.items())})


def scan_csv_once(path, spec):
    digest = hashlib.sha256()
    before = path.stat()
    with path.open('rb') as stream:
        def lines():
            for raw in stream:
                digest.update(raw)
                yield raw.decode('utf-8')
        reader = csv.DictReader(lines())
        require(reader.fieldnames is not None and len(reader.fieldnames) == len(set(reader.fieldnames)) and
                FIELDS <= set(reader.fieldnames), 'Bad CSV header')
        result = audit_rows(reader, spec)
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'CSV changed during audit')
    return dict(result, csv_sha256=digest.hexdigest(), csv_bytes=after.st_size, full_csv_passes=1)


def terminal_binding(terminal, digest):
    require(sha(terminal) == digest, 'Parent-specified terminal hash differs')
    data = read(terminal)
    require(data['status'] == WORKER_PASS and data['plan_sha256'] == PLAN_SHA and
            data['pins_unchanged'] is True and data['retries'] == 0 and
            data.get('error') is None and data.get('full_child_acceptance') is False,
            'Original terminal not accepted')
    results = data['results']
    require(len(results) == 1, 'Not exact one original result')
    result = results[0]
    require(result['name'] == NAME and result['status'] == 'PASS' and result['returncode'] == 0 and
            not result['reason'] and 0 <= result['elapsed_s'] <= 9000, 'Original result failed/incomplete')
    root = Path(result['artifact_dir'])
    require(root == terminal.parent/'replay/tests'/NAME, 'Unexpected artifact location')
    require(sha(terminal.parent/'plan.json') == PLAN_SHA, 'Terminal plan drift')
    required = [terminal.parent/'launch.json', terminal.parent/'replay/run.json',
                terminal.parent/'replay/summary.json']
    required += [root/n for n in ('input.elf', 'inputs.json', 'command.json', 'console.log',
                 'work/run.vcs.log', 'commit_trace.csv', 'trace_summary.json', 'strict_prefix.json')]
    require(set(data['evidence_pins']) == {str(p) for p in required}, 'Terminal evidence membership')
    csv_path = root/'commit_trace.csv'
    for path in required:
        if path != csv_path:
            require(sha(path) == data['evidence_pins'][str(path)], 'Terminal artifact drift: '+str(path))
    require(sha(root/'input.elf') == ELF_SHA, 'Private ELF differs')
    run = read(terminal.parent/'replay/run.json')
    require(run['status'] == 'COMPLETE' and run['status_counts'] == {'PASS': 1}, 'Original runner incomplete')
    require(read(terminal.parent/'replay/summary.json') == results, 'Original summary differs')
    original = read(root/'strict_prefix.json')
    raw = original['strict']
    require(raw['status'] == 'PASS_RAW112_FULL_SETUP_ORACLE' and raw['target_hits'] == 112 and
            raw['routine_retire_counts'] == [112]*13 and raw['returned_vstart_zero'] == 112 and
            raw['fullcap_checks'] == 114688 and raw['guards'] == 224 and
            raw['actual_output_scalar_loads'] == 114912 and raw['soc_ctrl_exit'] == 0 and
            len(raw['calls']) == 112, 'Original full oracle missing')
    require(original['csv_sha256'] == data['evidence_pins'][str(csv_path)], 'Original CSV identity disagreement')
    return data, original, csv_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    prepare = sub.add_parser('inventory', help='Static inputs only; never read DUT artifacts')
    prepare.add_argument('--out', type=Path, required=True)
    audit = sub.add_parser('terminal', help='Requires separate parent terminal authorization')
    audit.add_argument('--authorize-terminal-once', action='store_true', required=True)
    audit.add_argument('--terminal', type=Path, required=True)
    audit.add_argument('--terminal-sha256', required=True)
    audit.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    require(args.out.resolve().is_relative_to(HERE), 'Write only owned directory')
    require(not args.out.exists(), 'Fresh output required; never overwrite/retry')
    args.out.mkdir(parents=True)
    report = dict(status='NOT_ACCEPTED', scope='SUPPLEMENT_ONLY_NOT_WORKER_REPLACEMENT')
    try:
        spec = specification()
        save_new(args.out/'inventory.json', spec)
        if args.mode == 'inventory':
            report.update(status='STATIC_INVENTORY_ONLY_NOT_DUT', instruction_pcs=len(spec['instructions']),
                          helper_functions=len(spec['helpers']), source_pins=spec['source_pins'])
        else:
            terminal = args.terminal.resolve()
            data, original, csv_path = terminal_binding(terminal, args.terminal_sha256)
            observed = scan_csv_once(csv_path, spec)
            require(observed['csv_sha256'] == original['csv_sha256'], 'Full CSV hash differs')
            generic = original['generic']
            require((observed['rows'], observed['retired_rows'], observed['last_cycle']) ==
                    (generic['rows'], generic['retire_count'], generic['last_cycle']) ==
                    (original['strict']['csv_rows'], original['strict']['retired_rows'],
                     original['strict']['csv_last_cycle']), 'Original CSV counts differ')
            require(generic['vector_retire_count'] == 1236, 'Generic architectural vector count differs')
            require(sha(terminal) == args.terminal_sha256, 'Terminal changed during audit')
            for path, digest in spec['source_pins'].items():
                require(sha(path) == digest, 'Static input changed during audit')
            report.update(status='PASS_TERMINAL_PC_SUPPLEMENT_WITH_ORIGINAL_ORACLE',
                          terminal=str(terminal), terminal_sha256=args.terminal_sha256,
                          original_status=data['status'], original_evidence_pins=data['evidence_pins'],
                          observed=observed, source_pins=spec['source_pins'],
                          full_child_acceptance=False, data_oracle_rerun=False)
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
        save_new(args.out/'report.json', report)
        raise
    report['audit_script_sha256'] = sha(Path(__file__))
    save_new(args.out/'report.json', report)
    print(json.dumps({k: v for k, v in report.items() if k in ('status', 'instruction_pcs', 'helper_functions')}))


if __name__ == '__main__':
    main()
