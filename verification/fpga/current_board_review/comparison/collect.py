#!/usr/bin/env python3
"""Collect raw outcomes and bind the scalar commit trace to decoded instructions."""
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
IMAGE = Path('/home/wangwy/fpga_runs/current_board_integration_final01/campaign/image')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    image = json.loads((IMAGE / 'image.json').read_text())
    frozen = Path(image['snapshot']) / 'sources'
    results = []
    for name, run in [('active_snan', 'vcs_main01'), ('no_snan', 'vcs_main01'),
                      ('all_off', 'vcs_main01'), ('tail_vl15', 'vcs_tail01'),
                      ('prestart_snan', 'vcs_prestart01')]:
        directory = HERE / run / 'tests' / name
        console = (directory / 'console.log').read_text()
        result, = re.findall(r'^CMP_RESULT .*$', console, re.MULTILINE)
        fields = dict(re.findall(r'(\w+)=(\w+)', result))
        dis = (HERE / 'soc' / (name + '.dis')).read_text()
        op = 'op_4' if name == 'tail_vl15' else 'op_0'
        block, = re.findall(r'^\w+ <' + op + r'>:\n(.*?)(?=\n\w+ <)', dis, re.MULTILINE | re.DOTALL)
        target, = [line for line in block.splitlines() if 'vmfeq.' in line]
        match = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]+)', target)
        pc, opcode = match.groups()
        trace_path = directory / 'work/trace_hart_0.log'
        lines = trace_path.read_text().splitlines()
        index, = [i for i, line in enumerate(lines) if re.search(r'\b0*' + pc + r'\s+0\s+' + opcode + r'\b', line)]
        excerpt = '\n'.join(lines[index - 8:index + 9]) + '\n'
        (HERE / (name + '_target.txt')).write_text('OBJDUMP\n' + block + '\nSCALAR COMMIT TRACE\n' + excerpt)
        diagnostics = [line for line in console.splitlines() if line.startswith(('CMP_', 'RVV_FP_COMPARE_', 'BOARD_CASE_', 'BOARD_REPLAY_'))]
        runner, = [r for r in json.loads((HERE / run / 'summary.json').read_text()) if r['name'] == name]
        results.append(dict(name=name, run=run, result=fields, diagnostics=diagnostics,
                            target_pc='0x' + pc, target_opcode=opcode, target=target.strip(),
                            architectural_pass='BOARD_CASE_PASS ' + name in console,
                            checked_runner=runner,
                            flags_match=fields['expected_flags'] == fields['actual_flags'],
                            console_sha256=sha(directory / 'console.log'),
                            trace_sha256=sha(trace_path), elf_sha256=sha(HERE / 'soc' / (name + '.elf'))))
    refs = ['hardware/src/lane/vmfpu.sv', 'hardware/src/lane/lane.sv',
            'hardware/src/lane/lane_sequencer.sv', 'hardware/src/masku/masku.sv',
            'hardware/src/masku/masku_operands.sv', 'hardware/deps/fpnew/src/fpnew_opgroup_fmt_slice.sv',
            'hardware/deps/fpnew/src/fpnew_noncomp.sv', 'hardware/src/ara_dispatcher.sv']
    summary = dict(scope='current frozen SoC image architectural comparison flags; no new RTL/internal probes',
                   original_acceptance=False, image_directory=str(IMAGE),
                   image_ledger_sha256=sha(IMAGE / 'image.json'),
                   simv_sha256=image['files'][image['simv']], frozen_root=str(frozen),
                   frozen_rtl_sha256={p: sha(frozen / p) for p in refs},
                   results=results)
    campaign = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
    original_elf = campaign / 'rvv_additions28/binaries/rvv_fp_compare_e16_mf4'
    original_sha = sha(original_elf)
    if original_sha != '777190b9d2ea291329db61a01bee011ae389280d30c1437d9ad64901ad46d15f':
        raise ValueError('original board ELF drift')
    report = campaign / 'rvv_recovery08_07/resume/board_report_live07.json'
    board = json.loads(report.read_text())
    entry, = [r for r in board['results'] if r['name'] == 'rvv_fp_compare_e16_mf4']
    summary['original_all_off'] = dict(elf=str(original_elf), sha256=original_sha,
                                      report=str(report), report_sha256=sha(report), result=entry)
    (HERE / 'results.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps([r['result'] for r in results], indent=2))


if __name__ == '__main__':
    main()
