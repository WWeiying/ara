#!/usr/bin/env python3
"""Unchanged ELF numerical oracle plus native architectural trace checks; no RTL timing."""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
FIRMWARE = {
    'perf': ('stage4_features_full_call_build_perf_20261110_02',
             '8e3684c8163cc19eba9478c7bf1b5f17a3d2481b7b2349c06f5569591009c8d6',
             'a87b62b49d9f2a6bb5b4234306549b7c7ae06066b391be47542f025e0b3ef4bf'),
    'functional': ('stage4_features_full_call_build_functional_20261110_01',
                   '17d9a7a668b874c85732b6790220784fa6320c2403093a239b10721c1c72c23a',
                   '67ff3a891db35b1689f1436d2be483fd0ca86375c0738860227fcc411ed33a74')}
CHECK_SHA = 'f51a442aa54df4499e561fd9ee44bf0fa07f285ec87a1efd6b62d5bbe6710298'
FIXTURE_SHA = '54fee23e0371a7a45fcfbcd12563402569b06af4138dd8c65b3bdcae3d2048ab'
ELF_READER_SHA = '3317b30d500bef0cbeff9299001310ebe464ad4d1e53383aff0288f39af6dbb3'
LIBM_SHA = '9a48df5756070cc13f710fff77fbff6d35e45c52e29303bd506756cf341e6f26'
QBS_ELF = OUT / 'qemu-context-contract-20261023-01/qbs_contract_test.elf'
QBS_SHA = '402a395df2d13ddf5bce54cb183e5b9edb5ab279f50cee30a0e7cf230955dbc2'
QBS_SOURCES = {
    'qbs_contract_test.c': 'cd7611f8050c9947e9b87a355427721e3176b0e08b7a1dab9a179a62de1e0308',
    'qbs_contract_test.S': 'c194b16c650661b10b9400e2c2da10dd2a1286e4e80229e7db4ab11e38c1e929',
    'qbs_contract_test.ld': '7c478840ce7644e2a8cbe7202e6fd180ac0dd12648cc1caa35448f3a3018140d'}
TRACE = dict(info='index result', begin='seq pc insn rs1 rs2 frm fflags',
             read='seq pc address bytes', end='seq pc status fflags valid tile tokens tval')
HEX = set('result pc insn rs1 rs2 address tval'.split())
INFO = [1 | 1 << 8 | 64 << 16 | 8 << 24 | 8 << 32 | 1 << 40 | 15 << 48,
        0x5b | 2 << 8 | 3 << 11 | 4 << 14 | 5 << 17 | 6 << 20,
        2 | 64 << 8 | 8 << 16 | 6 << 24 | 127 << 32 | 1 << 40,
        0x5b | 6 << 8 | 7 << 11 | 128 << 16 | 1 << 24]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    def pairs(items):
        result = {}
        for k, v in items:
            require(k not in result, 'Duplicate JSON key')
            result[k] = v
        return result
    return json.loads(Path(path).read_text(), object_pairs_hook=pairs)


def load(path, expected, name):
    require(sha(path) == expected, 'Frozen dependency drift: ' + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stage4(kind, validate=True):
    name, receipt_sha, elf_sha = FIRMWARE[kind]
    path = OUT / name
    require(sha(path / 'build.json') == receipt_sha and sha(path / 'attention_features.elf') == elf_sha,
            'Unchanged Stage4 firmware identity')
    require(sha(path / 'inputs/fixture.py') == FIXTURE_SHA, 'Frozen fixture drift')
    checker = load(path / 'inputs/check.py', CHECK_SHA, 'unchanged_features_' + kind)
    report = checker.build_receipt(path) if validate else read(path / 'build.json')
    require(report['kind'] == kind and report['target_libm_sha256'] == LIBM_SHA, 'Target libm/kind changed')
    return path, report, checker, read(path / 'fixture.json')


def binding(kind, report=None):
    reader_path = OUT / FIRMWARE['perf'][0] / 'inputs/support/elf.py'
    reader = load(reader_path, ELF_READER_SHA, 'unchanged_elf_reader')
    path = QBS_ELF if kind == 'qbs' else OUT / FIRMWARE[kind][0] / 'attention_features.elf'
    require(sha(path) == (QBS_SHA if kind == 'qbs' else FIRMWARE[kind][2]), 'ELF drift')
    contract = reader.contract(path.read_bytes())
    starts, next_pc = {}, -1
    for pc, word in sorted(contract['words'].items()):
        if pc < next_pc:
            continue
        size = 4 if word & 3 == 3 else 2
        starts[pc] = word if size == 4 else word & 0xffff
        next_pc = pc + size
    custom = {pc: word for pc, word in starts.items() if word & 0x7f == 0x5b}
    require(custom, 'No native custom instructions in ELF')
    entries = {} if kind == 'qbs' else report['elf_contract']['entries']
    for name, row in entries.items():
        mask = 0xffffffff if row['insn'] & 3 == 3 else 0xffff
        require(starts.get(row['pc']) == row['insn'] & mask, 'Entry does not bind ELF: ' + name)
    return dict(custom=custom, entries=entries, points=sorted(set(custom) | {r['pc'] for r in entries.values()}))


def trace_events(text, points):
    events, cancelled = [], 0
    for line in text.splitlines():
        if line.startswith('Trace '):
            m = re.fullmatch(r'Trace (\d+): (0x[0-9a-f]+) \[[0-9a-f]+/([0-9a-f]+)/[0-9a-f]+/[0-9a-f]+\].*', line)
            require(m and int(m[1]) == 0 and int(m[3], 16) in points, 'Unexpected CPU/filtered exec trace')
            events.append(('exec', dict(pc=int(m[3], 16), tb=m[2])))
        elif line.startswith('Stopped execution of TB chain before '):
            m = re.fullmatch(r'Stopped execution of TB chain before (0x[0-9a-f]+) \[([0-9a-f]+)\].*', line)
            require(m and events and events[-1] == ('exec', dict(pc=int(m[2], 16), tb=m[1])),
                    'Cancelled TB does not match immediately preceding exec event')
            events.pop()
            cancelled += 1
        elif 'akv_arch_' in line:
            m = re.search(r'\bakv_arch_(\w+) (.+)$', line)
            require(m and m[1] in TRACE, 'Unknown architecture event')
            fields = {}
            for token in m[2].split():
                require(token.count('=') == 1, 'Malformed trace field')
                k, value = token.split('=')
                require(k in TRACE[m[1]].split() and k not in fields and
                        re.fullmatch(r'0x[0-9a-fA-F]+' if k in HEX else r'[0-9]+', value), 'Bad trace field')
                fields[k] = int(value, 16 if k in HEX else 10)
            require(set(fields) == set(TRACE[m[1]].split()), 'Incomplete architecture event')
            events.append((m[1], fields))
        elif 'riscv_cpu_do_interrupt:' in line:
            m = re.search(r'riscv_cpu_do_interrupt: hart:(\d+), async:(\d+), cause:([0-9a-f]+), '
                          r'epc:0x([0-9a-f]+), tval:0x([0-9a-f]+), desc=.+$', line)
            require(m and int(m[1]) == 0 and int(m[2]) == 0, 'Unexpected interrupt')
            events.append(('trap', dict(cause=int(m[3], 16), pc=int(m[4], 16), tval=int(m[5], 16))))
        else:
            require(not re.search(r'(?i)fatal|assertion|segmentation|Trace |akv_arch_', line), 'Malformed/fatal trace')
    return events, cancelled


def schedule(fixture, trial, groups, frozen):
    tr = fixture['trials'][trial]
    c = fixture['oracle']['cases'][tr['case']]['case']
    d, rows = c['dimension'], c.get('rows', c['heads'])
    on = tr['requested'] and not tr['frm']
    ops = []
    def add(insn, a, b, tile, tokens, valid=1, reads=(), flags=0):
        ops.append(dict(insn=insn, a=a, b=b, tile=tile, tokens=tokens, valid=valid,
                        reads=list(reads), flags=flags, frm=tr['frm']))
    for g in range(c['heads'] // rows):
        addresses = groups[(trial, g)]
        for tile in range(0, c['tokens'], 64):
            t = min(64, c['tokens'] - tile)
            reads = ([(addresses['q'] + h * 256, 2 * d) for h in range(rows)] if tile == 0 else [])
            reads += [(addresses[s] + (tile + i) * 256, 2 * d) for s in ('k', 'v') for i in range(t)]
            add(0x00b5605b if tile == 0 else 0x02a0605b, None if tile == 0 else 0, tile, tile, t, reads=reads)
            if on:
                for mode in ('QK', 'PV'):
                    for base in range(0, rows, 2):
                        h = min(2, rows - base)
                        command = dict(trial=trial, group=g, tile=tile, mode=mode, tokens=t, dimension=d, heads=h, base=base)
                        control = t - 1 | (h - 1) << 6 | {64: 0, 128: 1, 96: 2}[d] << 7
                        add(0x0605705b if mode == 'QK' else 0x0485705b,
                            control | (base << 9 if mode == 'QK' else 0), 0 if mode == 'QK' else None,
                            tile, t, flags=frozen.f.local_flags(fixture['oracle'], fixture['trials'], command))
            else:
                for _ in range(rows // 2):
                    for col in range(0, d, 4):
                        add(0x0205745b, col, 0, tile, t)
                if rows % 2:
                    for col in range(d):
                        add(0x0005745b, col, 0, tile, t)
                opcode = {64: 0x0005345b, 96: 0x0405345b, 128: 0x0205345b}[d]
                for _ in range(rows // 2):
                    for token in range(t):
                        add(opcode + (0x100 if token % 2 else 0), 2 + 4 * token, 0, tile, t)
                if rows % 2:
                    for token in range(t):
                        add(opcode, 2 + 4 * token, 0, tile, t)
        add(0x0000505b, 0, 0, tile, t, valid=0)
    return ops


def stage4_architecture(events, fixture, frozen, bound, groups, numbers):
    names = {row['pc']: name for name, row in bound['entries'].items()}
    trial, active, pending, live, sequence, done = -1, None, None, None, 0, []
    reads_total, info_total, resident_total = 0, 0, 0
    for tag, row in events:
        if tag == 'exec':
            pc = row['pc']
            if pc in names:
                name = names[pc]
                if name == 'feature_full_call':
                    require(active is None and pending is None and live is None, 'Overlapping full call')
                    trial += 1
                    require(trial < len(fixture['trials']), 'Extra full call')
                    active = dict(ops=schedule(fixture, trial, groups, frozen), pos=0,
                                  entries=Counter(dict.fromkeys((*frozen.ENTRY_NAMES, 'rotation_body'), 0)),
                                  info=Counter(), sticky=fixture['trials'][trial]['initial_flags'])
                elif name == 'feature_terminal_marker':
                    require(active is not None and pending is None and live is None and active['pos'] == len(active['ops']) and
                            active['info'] == Counter({i: 1 for i in range(4)}) and
                            dict(active['entries']) == frozen.expected_entries(fixture, fixture['trials'][trial]),
                            'Incomplete full call/entries/capability/work')
                    done.append(dict(active['entries']))
                    active = None
                else:
                    require(active is not None, 'SDK/leaf entry outside full call')
                    active['entries'][name] += 1
            if pc in bound['custom']:
                require(active is not None and pending is None and live is None, 'Unowned/overlapping native instruction')
                pending = (pc, bound['custom'][pc])
        elif tag == 'info':
            require(pending is not None and pending[1] & 0xfff0707f == 0x405b and
                    row['index'] in range(4) and row['result'] == INFO[row['index']], 'Native capability result mismatch')
            active['info'][row['index']] += 1
            info_total += 1
            pending = None
        elif tag == 'begin':
            require(active is not None and pending == (row['pc'], row['insn']) and live is None and
                    active['pos'] < len(active['ops']), 'Helper begin lacks actual native instruction')
            op = active['ops'][active['pos']]
            sequence += 1
            require(row['seq'] == sequence and row['insn'] == op['insn'] and row['frm'] == op['frm'] and
                    (op['a'] is None or row['rs1'] == op['a']) and (op['b'] is None or row['rs2'] == op['b']) and
                    row['fflags'] in range(32) and row['fflags'] & active['sticky'] == active['sticky'] and
                    row['fflags'] | (numbers['fcsr'][trial] & 31) == numbers['fcsr'][trial] & 31,
                    'Opcode/control/FRM/sticky flags mismatch')
            expected_reads = list(op['reads'])
            if op['a'] is None:
                require(0x80000000 <= row['rs1'] < 0x81000000 - 64 and row['rs1'] % 64 == 0,
                        'FULL descriptor outside admitted RAM/alignment')
                expected_reads.insert(0, (row['rs1'], 64))
            live = dict(op=op, begin=row, reads=expected_reads, index=0)
            pending = None
        elif tag == 'read':
            require(live is not None and live['index'] < len(live['reads']), 'Unexpected RAM read')
            address, size = live['reads'][live['index']]
            require(row == dict(seq=sequence, pc=live['begin']['pc'], address=address, bytes=size),
                    'FULL/REFILL snapshot address/size mismatch')
            live['index'] += 1
            reads_total += 1
        elif tag == 'end':
            require(live is not None and live['index'] == len(live['reads']), 'Missing snapshot reads/helper begin')
            op = live['op']
            require(row == dict(seq=sequence, pc=live['begin']['pc'], status=0, fflags=op['flags'],
                                valid=op['valid'], tile=op['tile'], tokens=op['tokens'], tval=0),
                    'Completion/local arithmetic flags/context lifecycle mismatch')
            active['sticky'] = live['begin']['fflags'] | row['fflags']
            active['pos'] += 1
            resident_total += int(op['insn'] in (0x0605705b, 0x0485705b))
            live = None
        else:
            raise ValueError('Trap/unknown event in positive Stage4 execution')
    require(active is pending is live is None and len(done) == len(fixture['trials']) and
            sequence == len(fixture['work']['legacy']) + len(fixture['work']['resident']) and
            resident_total == len(fixture['work']['resident']), 'Incomplete actual native calls')
    return dict(calls=len(done), legacy_commands=sequence - resident_total, resident_commands=resident_total,
                info_records=info_total, ram_reads=reads_total, actual_entries=done,
                local_flags_checked=True, snapshot_lifecycle_checked=True, instruction_attempts_not_rtl_retirements=True)


def qbs_schedule():
    result = [(0x0005155b, 0, 0)] * 5
    def emit(m, cause=0, tval=None, bad=False):
        word = 0x00b5005b | (m - 1) << 25 | (0x80 if bad else 0)
        result.append((word, cause, word if cause == 2 else (0x10000000 if cause == 5 and tval is None else tval or 0)))
    for cause, address in ((0, 0), (5, None), (5, None), (5, None), (0, 0), (5, 0x88000000), (5, 0x88000000)):
        emit(1, cause, address)
    for m in (1, 2, 3, 4, 5, 8):
        emit(m)
    emit(8, 2, bad=True)
    emit(1, 2)
    emit(2, 2, bad=True)
    for cause in (2, 0, 0, 0, 0, 2, 2, 2, 0, 0, 2, 0, 5, 2):
        emit(1, cause)
    for m, blocks, q8k in ((4, 1, False), (4, 28, False), (4, 32, False),
                           (5, 1, False), (5, 17, False), (8, 17, False), (4, 4, True)):
        for cause in (0, 0, 0, 0, 2, 0, 2, 0):
            emit(m, cause)
        emit(8 if m == 5 else 5 if m == 8 else 1, 2)
        for cause in (0, 2, 0):
            emit(m, cause)
        if q8k or blocks == 1:
            emit(m, 2)
            emit(m)
        for cause in (5, 0, 5, 0, 0, 2, 0, 0, 0):
            emit(m, cause)
    emit(2, 2)
    emit(3, 2)
    return result


def qbs_architecture(events, bound):
    expected, index, pending, traps = qbs_schedule(), 0, None, Counter()
    words = Counter()
    for tag, row in events:
        if tag == 'exec':
            require(pending is None and index < len(expected), 'Extra/missing QBS fault/instruction')
            word, cause, tval = expected[index]
            require(bound['custom'].get(row['pc']) == word, 'QBS native operation order differs')
            words[hex(word)] += 1
            index += 1
            pending = dict(pc=row['pc'], cause=cause, tval=tval) if cause else None
        elif tag == 'trap':
            require(pending == row, 'QBS real trap PC/cause/tval differs')
            traps[str(row['cause'])] += 1
            pending = None
        else:
            raise ValueError('Unexpected AKV helper in native QBS smoke')
    require(index == len(expected) and pending is None, 'Truncated native QBS contract smoke')
    return dict(native_instructions=index, opcode_counts=dict(words), traps=dict(traps),
                firmware_selfchecks=True, reused_unchanged_elf=True)


def check(kind, log, trace):
    text = Path(log).read_text()
    require(not re.search(r'(?i)fatal|assertion|segmentation|FEATURE_FAIL', text), 'Guest failure')
    if kind == 'qbs':
        for name, digest in QBS_SOURCES.items():
            require(sha(ROOT / 'verification/qbs/qemu' / name) == digest, 'QBS contract source drift')
        bound = binding(kind)
        events, cancelled = trace_events(Path(trace).read_text(), set(bound['points']))
        proof = dict(work=qbs_architecture(events, bound), elf_sha256=QBS_SHA)
    else:
        path, report, frozen, fixture = stage4(kind)
        numbers = frozen.numerical(text, fixture, (path / 'data.bin').read_bytes())
        numbers.pop('timing')
        groups = {}
        for line in text.splitlines():
            if line.startswith('FEATURE_GROUP '):
                row = frozen.parse(line[len('FEATURE_GROUP '):], frozen.SCHEMAS['GROUP'].split(), ('q', 'k', 'v', 'out'))
                require((row['trial'], row['group']) not in groups, 'Duplicate group record')
                groups[(row['trial'], row['group'])] = row
        bound = binding(kind, report)
        events, cancelled = trace_events(Path(trace).read_text(), set(bound['points']))
        proof = dict(numerical=numbers, work=stage4_architecture(events, fixture, frozen, bound, groups, numbers),
                     elf_sha256=report['elf_sha256'], original_numerical_checker_sha256=CHECK_SHA,
                     original_fixture_sha256=FIXTURE_SHA, target_libm_sha256=LIBM_SHA)
    return dict(state='NATIVE_ELF_ARCHITECTURE_CHECKED', kind=kind, **proof,
                log_sha256=sha(log), trace_sha256=sha(trace), cancelled_before_execution=cancelled,
                rtl_timing=False, rtl_protocol_checked=False, performance_acceptance=False,
                service_owner_checked=False, qemu_image_checked=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--kind', choices=('qbs', 'perf', 'functional'), required=True)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--trace', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.kind, args.log, args.trace), indent=2, sort_keys=True))
