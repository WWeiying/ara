#!/usr/bin/env python3
"""Recheck raw acceptance, archived source, exact assembly and full oracle reads."""
import csv
import difflib
from fractions import Fraction
import json
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
import check_continuation as terminal
from prepare_batch import HERE, ROOT, INTEGRATION, sha, save
from prepare_successor import narrow, symbol
from replay_candidate03 import oracle, read, require, pins_check

OUT = HERE / 'acceptance_audit01'
RUN = HERE / 'successor01/vcs_candidate04_remaining7_01'
OBJDUMP = ROOT / 'install/riscv-gcc/bin/riscv64-unknown-elf-objdump'


def instructions(elf, name):
    output = subprocess.check_output([str(OBJDUMP), '-d', str(elf)], text=True)
    active, rows = False, []
    for line in output.splitlines():
        header = re.match(r'^([0-9a-f]+) <([^>]+)>:', line)
        if header:
            if active:
                break
            active = header[2] == name
        if active:
            match = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]+)\s+(.+)', line)
            if match:
                rows.append(dict(pc=int(match[1],16), insn=match[2], text=match[3]))
    require(rows, 'Missing original assembly symbol '+name)
    return rows


def archived_window(elf, expected):
    output = subprocess.check_output([str(OBJDUMP), '-d', str(elf)], text=True)
    rows = []
    for line in output.splitlines():
        match = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]+)\s+(.+)', line)
        if match:
            rows.append(dict(pc=int(match[1],16), insn=match[2], text=match[3]))
    codes = [x['insn'] for x in expected]
    windows = [rows[i:i+len(codes)] for i in range(len(rows)-len(codes)+1)
               if [x['insn'] for x in rows[i:i+len(codes)]] == codes]
    require(len(windows) == 1, 'Stripped archived ELF does not contain one exact target routine')
    return windows[0]


def main():
    require(not OUT.exists(), 'Fresh independent audit required')
    control, results = terminal.validate(RUN, sha(RUN / 'plan.json'))
    accepted = control['results']+results
    completion = read(RUN / 'complete.json')
    require(completion['status'] == 'PASS_1_INHERITED_CONTROL_PLUS_7_CANDIDATE04' and
            completion['inherited_control'] == control and completion['results'] == results,
            'Independent terminal content differs')
    inventory = read(HERE / 'inventory83.json')
    lineage = read(HERE / 'lineage83.json')
    programs = read(HERE / 'successor01/soc01/programs.json')['programs']
    source = read(HERE / 'successor01/prepared01/provenance.json')
    host = read(HERE / 'successor01/host_semantics.json')['results']
    reference = read(HERE / 'successor01/reference01/reference.json')['results']
    sys.path.insert(0, str(INTEGRATION))
    from prepare import adapt
    pinned = dict(read(RUN / 'plan.json')['pins'])
    rows = []
    for case, result in zip(source['cases'], accepted):
        name = case['id']
        require(name == result['name'], 'Accepted source order differs')
        archived = case['original_case']
        record, = [r for r in inventory['records'] if r['case']['name'] == archived['name']]
        family, = [r for r in lineage['records'] if r['name'] == archived['name']]
        require(record['case'] == archived and record['raw_board']['exit_code'] == 1 and
                record['raw_board']['status'] == 'failed', 'Original board evidence differs')
        folder = Path(case['source_directory'])
        for file,digest in archived['scenario_sources'].items():
            require(sha(folder / file) == digest and
                    sha(HERE / 'successor01/prepared01' / name / 'original' / file) == digest,
                    name+': original source/assembly drift')
            pinned[str(folder / file)] = digest
        for file,digest in (('scenario.elf',archived['sha256']),
                            ('original.elf',archived['original_elf_sha256'])):
            require(sha(folder / file) == digest, name+': archived ELF drift')
            pinned[str(folder / file)] = digest
        require(sha(Path(family['original_c'])) == family['original_c_sha256'], 'Parent C identity drift')
        op = archived['selected_trial']['op']
        original_port = adapt((folder / 'scenario.c').read_text(), name)
        port = (HERE / 'successor01/prepared01' / name / 'case.c').read_text()
        require(port == narrow(original_port, op), name+': non-loop port difference')
        expected_diff = ''.join(difflib.unified_diff(original_port.splitlines(True), port.splitlines(True),
            fromfile='prepared01/'+name+'/case.c', tofile='successor01/prepared01/'+name+'/case.c'))
        require((HERE / 'successor01/source_diffs' / (name+'.diff')).read_text() == expected_diff,
                name+': source diff differs')
        elf = Path(programs[name]['path'])
        current_asm = instructions(elf, name+'_op_'+str(op))
        original_asm = archived_window(folder / 'scenario.elf', current_asm)
        require([x['insn'] for x in current_asm] == [x['insn'] for x in original_asm],
                name+': archived target assembly encoding differs')
        target, = [x for x in current_asm if x['text'].startswith(('vrgather.', 'vrgatherei16.'))]
        src = terminal.CONTROL / 'control/replay/tests' / name if name == terminal.NAMES[0] else \
              RUN / 'remaining7/replay/tests' / name
        cap = int(Fraction(archived['lmul'].replace('mf','1/').replace('m',''))*1024/archived['sew'])
        expected, = [x for x in host if x['name'] == name]
        require(expected['capacity'] == cap, 'Capacity differs')
        output, _ = symbol(elf, 'output', OBJDUMP)
        width = archived['sew']//8
        values = {output+width*i:v for i,v in enumerate([91]+expected['full_cap_expected']+[91])}
        observed, hits, csr, regs = {}, [], [], {}
        for item in csv.DictReader((src / 'commit_trace.csv').open()):
            if item['event'] != 'retire':
                continue
            pc, rd = int(item['pc'],16), int(item['rd'])
            value = int(item['rd_wdata'],16)
            if pc == target['pc']:
                require(item['insn'] == target['insn'] and regs[13] == 2 and regs[17] == 1,
                        name+': target identity/VL/vstart differs')
                hits.append(dict(pc=hex(pc), cycle=int(item['cycle']), insn=item['insn'],
                                 vl=regs[13], vstart=regs[17]))
            if any(pc == x['pc'] and x['text'].startswith('csrr\ta0,vstart') for x in current_asm):
                require(value == 0, name+': returned vstart differs')
                csr.append(dict(pc=hex(pc), cycle=int(item['cycle']), value=value))
            address = int(item['mem_addr'],16)
            if item['mem_rmask'] != '00' and address in values:
                require(value & ((1 << archived['sew'])-1) == values[address], name+': full oracle read differs')
                observed[address] = value & ((1 << archived['sew'])-1)
            if rd:
                regs[rd] = value
        require(len(hits) == len(csr) == 1 and set(observed) == set(values),
                name+': incomplete full-cap/guard/target evidence')
        ref, = [x for x in reference if x['name'] == name]
        log = HERE / 'successor01/reference01' / (name+'.log')
        require(sha(log) == ref['log_sha256'] and ref['returncode'] == 0 and
                oracle(programs[name], log.read_text()), name+': Spike full oracle differs')
        for file in ('console.log', 'commit_trace.csv', 'input.elf', 'inputs.json', 'command.json', 'work/run.vcs.log'):
            pinned[str(src / file)] = sha(src / file)
        rows.append(dict(name=name, status='PASS', original_case=archived, lineage=family,
            artifacts=str(src), target=hits[0], returned_vstart=csr[0], capacity=cap,
            scalar_output_reads=cap, both_guards_read=True, full_oracle_retained=True,
            archived_assembly_encoding_identical=True, target_routine_instructions=len(current_asm),
            archived_target_routine_pc=hex(original_asm[0]['pc']), elapsed_s=result['elapsed_s'],
            soc_elf_sha256=result['elf_sha256'], source_diff_sha256=sha(
                HERE / 'successor01/source_diffs' / (name+'.diff'))))
    pins_check(pinned)
    OUT.mkdir()
    save(OUT / 'audit.json', dict(status='PASS_8_SOURCE_FULLORACLE_IDENTITY_AUDIT', results=rows,
        candidate04_plan_sha256=sha(RUN / 'plan.json'), control_reused_not_rerun=True,
        original83=83, accepted_singles=8, remaining_singles=75, pins_verified=len(pinned),
        old_candidate03_status=read(HERE / 'vcs_candidate03_01/complete.json')['status'],
        old_candidate04_wrapper_status=read(terminal.CONTROL / 'complete.json')['status'],
        scope='Eight exact source singles; not original Linux ELF/parent matrices/board/83 closure'))
    save(OUT / 'pins.json', pinned)
    print('PASS_8_SOURCE_FULLORACLE_IDENTITY_AUDIT', OUT, flush=True)


if __name__ == '__main__':
    main()
