#!/usr/bin/env python3
"""Build02-only VCS boundary supplement. Illegal instructions do not retire."""
import argparse
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cases
import generate as g

require, sha = g.require, g.sha
BUILD = g.OUT/'resident_pv_soc_boundary_build_20261109_02'
BUILD_SHA = '7a6ba64e77c7fa4d6ce52602d992484d83c8b844d631dfd4cd9f2d8c41fb751c'
ELF_SHA = '6f5ac1eee0cd9a69a19ae02df55dc900dc490efd8af008e6d780a6dd156f30d5'
OLD_SHA = '095711476870d724f54639627ea535f934a6fac27c319c54e37387bc3d4a8fd0'
require(sha(HERE/'check.py') == OLD_SHA, 'Sealed boundary checker drift')
old = g.load(HERE/'check.py', 'boundary_sealed_checker_vcs')
FAULT_SYMBOLS = dict(boundary_pv_fault_pc=cases.PV_INSN, boundary_pv_rd2_pc=0x0485715b,
                     boundary_pv_vs2v4_pc=0x0445705b, boundary_pv_alias_pc=0x0485745b)
ISSUE_READS = (
    ('before_vl', 0xa4, 0xc20), ('before_vtype', 0xac, 0xc21),
    ('before_fcsr', 0xbc, 0x003), ('before_vstart', 0xc4, 0x008),
    ('before_mstatus', 0xec, 0x300), ('after_mstatus', 0x11c, 0x300),
    ('after_vl', 0x134, 0xc20), ('after_vtype', 0x13c, 0xc21),
    ('after_fcsr', 0x144, 0x003), ('after_vstart', 0x14c, 0x008))
TRAP_READS = (('cause', 0x1c, 0x342, 6), ('pc', 0x24, 0x341, 7),
    ('trap_mstatus', 0x2c, 0x300, 28), ('mtval', 0x4c, 0x343, 28),
    ('trap_fcsr', 0x54, 0x003, 28), ('trap_vstart', 0x5c, 0x008, 28))


def elf_contract(raw):
    require(len(raw) >= 64 and raw[:7] == b'\x7fELF\x02\x01\x01', 'Expected ELF64 little endian')
    h = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    require(h[1:4] == (2, 243, 1) and h[11] == 64 and h[6]+h[11]*h[12] <= len(raw), 'ELF header/bounds')
    sections = [struct.unpack_from('<IIQQQQIIQQ', raw, h[6]+i*h[11]) for i in range(h[12])]
    wanted, found = {'boundary_issue', 'boundary_trap', *FAULT_SYMBOLS}, {}
    for sec in sections:
        if sec[1] != 2:
            continue
        require(sec[9] == 24 and sec[5] % 24 == 0 and sec[4]+sec[5] <= len(raw) and sec[6] < len(sections), 'ELF symtab bounds')
        strings = sections[sec[6]]
        require(strings[1] == 3 and strings[4]+strings[5] <= len(raw), 'ELF strtab bounds')
        names = raw[strings[4]:strings[4]+strings[5]]
        for offset in range(sec[4], sec[4]+sec[5], 24):
            name, info, _, index, value, size = struct.unpack_from('<IBBHQQ', raw, offset)
            end = names.find(b'\0', name)
            require(name < len(names) and end >= name, 'ELF symbol name bounds')
            text = names[name:end].decode('ascii')
            if text not in wanted:
                continue
            require(text not in found and 0 < index < len(sections) and info >> 4 == 1, 'Invalid/duplicate ELF symbol')
            target = sections[index]
            require(target[2] & 4 and target[4]+target[5] <= len(raw) and
                target[3] <= value < target[3]+target[5], 'Symbol outside executable section')
            if text in ('boundary_issue', 'boundary_trap'):
                require(info & 15 == 2 and size > 0 and size % 4 == 0 and
                    value+size <= target[3]+target[5], 'Invalid function extent')
            found[text] = (value, size, target)
    require(set(found) == wanted, 'Missing boundary ELF symbols')
    words, ranges = {}, {}
    for name in ('boundary_issue', 'boundary_trap'):
        address, size, section = found[name]
        ranges[name] = (address, address+size)
        for pc in range(address, address+size, 4):
            words[pc] = struct.unpack_from('<I', raw, section[4]+pc-section[3])[0]
    issue, trap = ranges['boundary_issue'][0], ranges['boundary_trap'][0]
    fault_pc = {str(insn): found[name][0] for name, insn in FAULT_SYMBOLS.items()}
    require(all(words.get(pc) == int(insn) for insn, pc in fault_pc.items()), 'Fault PC/ELF instruction mismatch')
    require(words[issue] == 0xfc010113 and words[ranges['boundary_issue'][1]-4] == 0x00008067 and
        words[trap] == 0xfe010113 and words[trap+0xb8] == 0x30200073, 'Build02 entry/return contract drift')
    for _, offset, csr in ISSUE_READS:
        require(words[issue+offset] == csr << 20 | 6 << 7 | 0x2073, 'Build02 issue CSR PC/word mismatch')
    for _, offset, csr, rd in TRAP_READS:
        require(words[trap+offset] == csr << 20 | rd << 7 | 0x2073, 'Build02 trap CSR PC/word mismatch')
    return dict(words=words, ranges=ranges, issue=issue, trap=trap,
        issue_return=ranges['boundary_issue'][1]-4, resume=issue+0x114, mret=trap+0xb8, fault_pc=fault_pc)


def verified_build(build):
    build = Path(build).resolve(strict=True)
    require(build == BUILD and sha(build/'build.json') == BUILD_SHA, 'Only the sealed GNU build02 is accepted')
    receipt = json.loads((build/'build.json').read_text())
    require(receipt['state'] == 'BOUNDARY_SOFTWARE_BUILT_NOT_EXECUTED' and
        receipt['source_pins_sha256'] == sha(build/'source-pins.json') and
        receipt['elf_sha256'] == ELF_SHA and sha(receipt['elf']) == ELF_SHA, 'Build02 receipt/ELF identity drift')
    g.verify(json.loads((build/'source-pins.json').read_text()))
    g.verify(receipt['artifacts'])
    actual = {str(p): sha(p) for p in build.rglob('*') if p.is_file() and p != build/'build.json'}
    require(actual == receipt['artifacts'], 'Build02 artifact inventory drift')
    contract = elf_contract(Path(receipt['elf']).read_bytes())
    require(contract['fault_pc'] == receipt['fault_pc'], 'Receipt fault PCs disagree with ELF')
    return receipt, json.loads((build/'vectors/vectors.json').read_text()), contract


def case_records(text):
    return [old.fields(line[len('PV_BOUNDARY_CASE '):], old.CASE_FIELDS, old.CASE_HEX)
            for line in text.splitlines() if line.startswith('PV_BOUNDARY_CASE ')]


def pv(insn):
    return insn & 0x707f == 0x705b and insn >> 25 == 2


def sample(rows, pc, rd, expected, contract):
    selected = [row for row in rows if int(row['pc'], 16) == pc]
    require(len(selected) == 1, 'Missing/duplicate exact-PC CSR or counter sample')
    row = selected[0]
    require(int(row['insn'], 16) == contract['words'][pc] and int(row['rd']) == rd and
        int(row['trap']) == 0 and int(row['rd_wdata'], 16) == expected, 'Wrong instruction/rd/CSR/counter value')


def validate_attempt(rows, offered, spec, record, contract):
    require((record['id'], record['phase']) == (spec['id'], spec['phase']), 'Attempt/log identity mismatch')
    issue, trap = contract['issue'], contract['trap']
    for field, offset, _ in ISSUE_READS:
        sample(rows, issue+offset, 6, record[field], contract)
    sample(rows, issue+0x1a0, 10, spec['error'], contract)  # Load the real observation.traps counter.
    retired = [row for row in rows if pv(int(row['insn'], 16))]
    handler = [row for row in rows if contract['ranges']['boundary_trap'][0] <= int(row['pc'], 16) <
               contract['ranges']['boundary_trap'][1]]
    off = spec['error'] and spec['kind'] in ('fs_off', 'vs_off')
    require(len(offered) == (0 if off else 1), 'FS/VS-off escaped admission or missing/extra PV arch_start')
    seq = None
    if offered:
        require(int(offered[0]['insn'], 16) == spec['instruction'], 'PV architectural instruction mismatch')
        seq = int(offered[0]['order'])
        require(seq >= 0, 'Invalid architectural sequence')
    if not spec['error']:
        require(not handler and len(retired) == 1 and int(retired[0]['insn'], 16) == cases.PV_INSN and
            int(retired[0]['pc'], 16) == contract['fault_pc'][str(cases.PV_INSN)] and int(retired[0]['trap']) == 0,
            'Missing/extra successful PV retirement or unexpected handler')
        return seq, None
    require(not retired, 'Illegal PV must not have a fabricated RVFI retirement')
    expected_path = list(range(trap, trap+0xbc, 4))
    if off:
        first = 0x40 if spec['kind'] == 'fs_off' else 0x4c
        expected_path = [pc for pc in expected_path if not trap+first <= pc < trap+0x6c]
    require([int(row['pc'], 16) for row in handler] == expected_path, 'Missing/extra/wrong trap handler execution path')
    for field, offset, _, rd in TRAP_READS[:3] if off else TRAP_READS:
        sample(handler, trap+offset, rd, record[field], contract)
    fault_pc = contract['fault_pc'][str(spec['instruction'])]
    require(record['cause'] == 2 and record['pc'] == fault_pc, 'Wrong exact illegal cause/PC')
    for offset, rd, expected in ((0x6c, 6, 2), (0x78, 28, fault_pc), (0x80, 28, 1),
                                 (0x8c, 28, 0), (0x9c, 6, contract['resume'])):
        sample(handler, trap+offset, rd, expected, contract)
    return seq, dict(id=spec['id'], phase=0, cause=2, fault_pc=fault_pc,
        handler_entry=trap, recovery_mret=contract['mret'], trap_mstatus=record['trap_mstatus'],
        csr_accessible=not off, fcsr=None if off else record['trap_fcsr'],
        fflags=None if off else record['trap_fcsr'] & 31, vstart=None if off else record['trap_vstart'],
        arch_seq=seq, first_cycle=int(handler[0]['cycle']), last_cycle=int(handler[-1]['cycle']))


def architecture(commit_path, text, vectors, contract):
    specs, records = cases.attempts(vectors['cases']), case_records(text)
    require(len(specs) == len(records) == 33, 'Expected 33 attempted calls/log records')
    active, rows, offers, arch, traps, flow, used, windows = None, [], [], [], [], [], set(), []
    previous, retired_order, successful = -1, -1, 0
    for row in old.csv_rows(commit_path):
        cycle, insn = int(row['cycle']), int(row['insn'], 16)
        require(cycle >= previous, 'Nonmonotonic commit trace')
        previous = cycle
        if row['event'] == 'arch_start' and pv(insn):
            require(active is not None, 'PV request outside an actual boundary_issue call')
            offers.append(row)
        if row['event'] != 'retire':
            continue
        order, pc = int(row['order']), int(row['pc'], 16)
        require(order > retired_order, 'Repeated/out-of-order CPU retirement')
        retired_order = order
        context = insn & 0x7f == 0x5b and (insn >> 12) & 7 in (5, 6)
        if context or insn in (cases.QBS_INSN, cases.VADD_INSN):
            require(int(row['trap']) == 0, 'Context/postlude trapped')
            flow.append(insn)
        if pc == contract['issue']:
            require(active is None and len(arch) < 33, 'Nested/extra boundary_issue call')
            active = len(arch)
            rows, offers = [], []
        if active is None:
            require(not pv(insn) and pc not in contract['words'], 'Unowned PV/handler/issue retirement')
            continue
        require(pc in contract['words'] and insn == contract['words'][pc] and int(row['trap']) == 0,
                'Unexpected/trapped instruction in boundary_issue or handler')
        rows.append(row)
        if pc == contract['issue_return']:
            spec = specs[active]
            seq, group = validate_attempt(rows, offers, spec, records[active], contract)
            if seq is not None:
                require(seq not in used, 'Repeated PV architectural identity')
                used.add(seq)
            arch.append(seq)
            windows.append(dict(id=spec['id'], phase=spec['phase'], arch_seq=seq,
                begin_cycle=int(rows[0]['cycle']), end_cycle=int(rows[-1]['cycle']),
                offer_cycle=int(offers[0]['cycle']) if offers else None))
            if group:
                traps.append(group)
            else:
                successful += 1
            # This token denotes a CSR-proven trap, never a fake retire CSV row.
            flow.append(spec['instruction'])
            active = None
    require(active is None and len(arch) == 33 and len(traps) == 12 and successful == 21 and len(used) == 31,
            'Incomplete success/trap/request accounting')
    require(flow == cases.instruction_flow(vectors['cases']), 'Context lifetime/recovery/postlude flow mismatch')
    return arch, used, dict(successful_pv_retirements=21, faulting_pv_retirements=0,
        real_csr_trap_groups=12, pv_arch_start=31, fs_vs_off_without_arch_start=2,
        actual_fill_retirements=flow.count(cases.FILL_INSN), actual_release_retirements=flow.count(cases.RELEASE_INSN),
        groups=traps, attempts=windows,
        convention='Frozen CVA6 illegal cause2 has RVFI valid=0; CSR instructions retire normally')


def check_work(vector_path, commit_path, text, vectors, contract):
    specs = cases.attempts(vectors['cases'])
    probes = old.check_probes(text, specs)
    arch, consumed, trap_architecture = architecture(commit_path, text, vectors, contract)
    groups, qbs_rows, vadd_rows = old.defaultdict(list), [], []
    previous, config = -1, 0
    for row in old.csv_rows(vector_path):
        cycle, event, insn = int(row['cycle']), row['event'], int(row['insn'], 16)
        require(cycle >= previous and (row['nr_lanes'], row['vlen_bits']) == ('4', '1024'), 'Trace epoch/config drift')
        previous = cycle
        if event == 'config':
            require(config == 0 and cycle == 0, 'Repeated vector epoch')
            config += 1
            continue
        require(config == 1 and event in ('alloc', 'write', 'done'), 'Unknown vector event/reset')
        if pv(insn):
            require(insn == cases.PV_INSN, 'Backend PV instruction not the exact accepted request')
            groups[int(row['arch_seq'])].append(row)
        elif insn == cases.QBS_INSN:
            qbs_rows.append(row)
        elif insn == cases.VADD_INSN:
            vadd_rows.append(row)
    require(config == 1 and set(groups) <= consumed, 'Unowned PV allocation/write')
    probe_index, maintenance = 0, 0
    for seq, spec, window in zip(arch, specs, trap_architecture['attempts']):
        rows = groups.get(seq, [])
        if spec['error'] and spec['rejection'] == 'frontend':
            require(not rows, 'Frontend illegal reached backend')
            continue
        require(rows and window['offer_cycle'] <= int(rows[0]['cycle']) and
            int(rows[-1]['cycle']) <= window['end_cycle'], 'PV backend outside its real CPU attempt')
        uops = old.split_uops(rows)
        require(len(uops) == (7 if spec['kind'] == 'mixed' else 1), 'Unexpected maintenance/final allocation count')
        for index, uop in enumerate(uops[:-1]):
            reg = 8+index
            chunk = spec['source'][64*index:64*(index+1)]
            data = {(l, reg*4+w): old.word16(chunk, l, w) for l in range(4) for w in range(4)}
            old.audit_uop(uop, reg, 64, 1, data, source=3)
            maintenance += 1
        data = {(l, h*8+w): old.word16(spec['expected'][h*spec['dimension']:(h+1)*spec['dimension']], l, w)
            for l in range(4) for h in range(spec['heads']) for w in range(spec['dimension']//16)}
        vid = old.audit_uop(uops[-1], 0, 256, 1, data, writes=not spec['error'])
        require(vid == probes[probe_index]['vid'], 'PV probe/vector VID mismatch')
        probe_index += 1
    require(probe_index == 24 and maintenance == 6, 'Missing/extra admitted PV/maintenance work')
    require(qbs_rows and int(qbs_rows[0]['cycle']) > max(int(row['cycle']) for rs in groups.values() for row in rs),
            'QBS did not follow PV')
    qbs_data = [0x43800000, 0x44000000, 0x44400000]+[0]*29
    data = {(l, 32+w): qbs_data[8*w+l] | qbs_data[8*w+l+4] << 32 for l in range(4) for w in range(4)}
    old.audit_uop(qbs_rows, 8, 32, 2, data)
    require(vadd_rows and int(vadd_rows[0]['cycle']) > int(qbs_rows[-1]['cycle']), 'RVV did not follow QBS')
    data = {(l, 64+w): (0x10203041+3*(8*w+l)) | (0x10203041+3*(8*w+l+4)) << 32 for l in range(4) for w in range(4)}
    old.audit_uop(vadd_rows, 16, 32, 2, data, source=0)
    return dict(admitted_pv=24, frontend_rejected=9, backend_rejected=3, maintenance_uops=6,
        actual_qbs_alloc_done=1, actual_rvv_alloc_done=1, command_local_flags_checked=True,
        actual_vrf_data_checked=True, same_context_recoveries=11, released_context_reloads=1,
        actual_fill_retirements=22, actual_release_retirements=22), trap_architecture


def check_run(build_dir, log_path, vector_path, commit_path):
    build_dir, log_path, vector_path, commit_path = map(Path, (build_dir, log_path, vector_path, commit_path))
    receipt, vectors, contract = verified_build(build_dir)
    inputs = (build_dir/'build.json', build_dir/'source-pins.json', Path(receipt['elf']),
        build_dir/'vectors/vectors.json', log_path, vector_path, commit_path, HERE/'check.py',
        HERE/'check_vcs.py', HERE/'test_check_vcs.py')
    pins = {str(p.resolve()): sha(p) for p in inputs}
    text = log_path.read_text()
    numerical = old.check_log(text, vectors, contract['fault_pc'])
    work, trap_architecture = check_work(vector_path, commit_path, text, vectors, contract)
    g.verify(pins)
    return dict(schema='resident-pv-soc-boundary-vcs-v1', numerical=numerical, work=work,
        trap_architecture=trap_architecture, evidence_sha256=pins, protocol_checked=False,
        scope='Build02 successful retire + actual trap CSR evidence supplement; independent protocol audit required')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('build', 'log', 'vector', 'commit'):
        p.add_argument('--'+name, type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(check_run(args.build, args.log, args.vector, args.commit), indent=2))
