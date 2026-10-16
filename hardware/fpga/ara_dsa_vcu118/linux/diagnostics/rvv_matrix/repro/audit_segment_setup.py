"""Locate original misaligned-segment traps without attributing them to the target."""
import argparse
import json
from pathlib import Path
import re
import subprocess
from audit_slide import require
from match_exceptions import fault_records
from trace_masks import sha


def inspect(case, result, disassembly):
    records = fault_records(result.get('output', ''))
    require(result['status'] == 'failed' and len(records) == 1, 'Missing unique original trap')
    trap, = records
    instructions = []
    for line in disassembly.splitlines():
        match = re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+(\S+)\s*(.*)$', line)
        if match:
            instructions.append(dict(pc=int(match[1], 16), opcode=match[2],
                                     mnemonic=match[3], operands=match[4].replace(' ', '')))
    hits = [i for i, row in enumerate(instructions) if row['pc'] == trap['epc']]
    require(len(hits) == 1, 'Trap PC not uniquely decoded')
    i, = hits
    row = instructions[i]
    sew = case['sew']
    require(row['mnemonic'] == f'vle{sew}.v' and row['operands'] == 'v24,(a6)',
            'Not the measured preparation load')
    require(i >= 3 and instructions[i-3]['mnemonic'] == 'vsetvli' and
            instructions[i-3]['operands'] == f't0,a4,e{sew},{case["lmul"]},tu,mu' and
            instructions[i-2]['mnemonic'] == 'slli' and
            instructions[i-1]['mnemonic'] == 'mv' and instructions[i-1]['operands'] == 'a6,a1',
            'Preparation prelude differs')
    require(not any(x['mnemonic'] == 'vsetvli' and x['operands'].startswith('t0,a4,')
                    for x in instructions[:i-3]), 'Trap is not in the first operation')
    later = instructions[i+1:]
    target = next((x for x in later if x['mnemonic'].startswith('vlseg')), None)
    require(target is not None and target['mnemonic'] == f'vlseg3e{sew}.v', 'Missing later segment target')
    def register(name):
        values = re.findall(r'\b' + name + r'\s*:\s*([0-9a-f]+)', trap['output'])
        require(len(values) == 1, 'Missing or ambiguous trap register ' + name)
        return int(values[0], 16)
    require(trap['signal'] == 7 and trap['cause'] == 4, 'Not a load-address misalignment trap')
    require(trap['tval'] == register('a6') == register('a1') and trap['tval'] % (sew // 8) == 1,
            'Misaligned preparation address differs')
    require(register('t0') == register('a4') > 0 and register('a3') == 0,
            'Expected active preparation and zero-length target arguments')
    return dict(name=case['name'], original_elf_sha256=case['sha256'],
                trap_pc=hex(trap['epc']), trap_opcode=row['opcode'],
                trap_instruction=row['mnemonic'] + ' ' + row['operands'],
                signal=trap['signal'], cause=trap['cause'], bad_address=hex(trap['tval']),
                misalignment_bytes=1, preparation_vl=register('a4'), target_vl_argument=0,
                later_target_pc=hex(target['pc']), later_target_instruction=target['mnemonic'],
                classification='preparation_alignment_trap_not_segment_target_evidence',
                architectural_bug_proven=False, reduced_board_reproduction_confirmed=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('original', 'report', 'out'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--cross', required=True)
    a = p.parse_args()
    manifest = json.loads((a.original / 'manifest.json').read_text())
    raw = json.loads(a.report.read_text()); report = raw.get('report', raw)
    inputs = {c['name']: c for c in report['inputs']['cases']}
    results = {r['name']: r for r in report['results']}
    require(len(inputs) == len(report['inputs']['cases']) and len(results) == len(report['results']),
            'Duplicate report identity')
    a.out.mkdir(exist_ok=False)
    rows = []
    for c in manifest['cases']:
        require(c['name'].startswith('rvv_segments_misaligned_'), 'Wrong original family')
        binary = a.original / 'overlay/opt/ara-tests' / c['name']
        require(sha(binary) == c['sha256'] == inputs[c['name']]['sha256'], 'Original/deployed ELF differs')
        dis = subprocess.check_output([a.cross + 'objdump', '-d', str(binary)], text=True)
        rows.append(inspect(c, results[c['name']], dis))
        (a.out / (c['name'] + '.dis')).write_text(dis)
    require(rows, 'Empty original family')
    (a.out / 'original_report.json').write_bytes(a.report.read_bytes())
    audit = dict(original_manifest_sha256=sha(a.original / 'manifest.json'),
                 report_sha256=sha(a.report), cases=rows,
                 scope='Original ELF and recorded trap only; no reduced board equivalence claim',
                 specification='https://docs.riscv.org/reference/isa/unpriv/v-st-ext')
    (a.out / 'symptoms.json').write_text(json.dumps(audit, indent=2) + '\n')
    print('ORIGINAL_PREPARATION_TRAPS', len(rows), 'NOT_ESTABLISHED_RTL_BUGS')


if __name__ == '__main__':
    main()
