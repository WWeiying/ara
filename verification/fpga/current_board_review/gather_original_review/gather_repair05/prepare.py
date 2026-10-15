#!/usr/bin/env python3
"""Build two independently pinned source singles, never build an image or launch DUT."""
import difflib
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
HERE = OUT.parent
sys.path.insert(0, str(HERE))
import prepare_batch as base
from audit_accepted8 import instructions, archived_window, OBJDUMP
from prepare_successor import SPIKE, symbol

ARCHIVED = HERE / 'stall_prefix2_03/prepared/gather_prefix_e8_m4_ops20/original'
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate04/campaign/image')
NAMES = ['gather_probe_e8_m4_ops20_start128', 'gather_probe_e8_m4_ops20_start0']


def main():
    prepared = OUT / 'prepared'
    prepared.mkdir(exist_ok=False)
    source = (OUT / 'case.c').read_text()
    canonical = (ARCHIVED / 'scenario.c').read_text()
    assert base.sha(ARCHIVED / 'scenario.c') == 'b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca'
    sys.path.insert(0, str(base.INTEGRATION))
    from prepare import adapt
    adapted = adapt(canonical, 'REPAIR')
    # All modifications are reversible scope/identity/control changes, not oracle changes.
    reverted = source.replace(source[:source.index('#include <stdint.h>')],
                              adapted[:adapted.index('#include <stdint.h>')], 1)
    reverted = reverted.replace('#include "operations.h"\ntypedef uint8_t word;\n',
                                adapted[adapted.index('#ifndef RESTART_PERMUTATIONS'):adapted.index('static word input')])
    reverted = reverted.replace('int REPAIR_MAIN(void)', 'int REPAIR_main(void)')
    for narrow, original in (
        ('seed<1', 'seed<3'), ('op=20;op<21', 'op=0;op<OP_COUNT'),
        ('s<1', 's<8'), ('l=4;l<5', 'l=0;l<7'), ('mode<1', 'mode<4'),
        ('trial=1;trial<2', 'trial=0;trial<(RESTART_PERMUTATIONS ? 4U:1U)'),
    ):
        assert reverted.count(narrow) == 1
        reverted = reverted.replace(narrow, original)
    reverted = reverted.replace('#if REPAIR_START_ZERO\n            start=0;\n#endif\n', '')
    assert reverted == adapted, 'Unexpected change to original RNG/setup/oracle/statistics'
    (OUT / 'source.diff').write_text(''.join(difflib.unified_diff(adapted.splitlines(True), source.splitlines(True),
        fromfile='original_adapted.c', tofile='case.c')))
    cases = []
    model = json.loads((HERE / 'stall_prefix2_03/gather_prefix_e8_m4_ops20.host_expected.json').read_text())
    specs = []
    for number, name in enumerate(NAMES):
        folder = prepared / name
        shutil.copytree(ARCHIVED, folder / 'original')
        shutil.copyfile(OUT / 'case.c', folder / 'case.c')
        expected = dict(model['rows'][65])
        expected['ordinal'] = 1
        if number:
            expected['vstart'] = 0
            expected['output'] = [model['input'][index] if index < 512 else 0
                                  for index in model['indices16'][:256]] + [91] * 256
        base.save(OUT / (name + '.expected.json'), dict(model, rows=[expected]))
        cases.append(dict(id=name, assembly='operations.S',
            defines=['SEW=8', 'RESTART_PERMUTATIONS=1', 'PERMUTE_OP_MASK=1048576',
                     'REPAIR_MAIN='+name+'_main', 'REPAIR_START_ZERO='+str(number)],
            pass_markers=['RVV_PERMUTE_PASS sew=8 cases=1 errors=0',
                          'BOARD_CASE_PASS '+name, 'BOARD_REPLAY_PASS']))
        specs.append(dict(name=name, tuple=[0,20,0,4,0,1], actual_vstart=128 if number == 0 else 0,
                          control_override=bool(number), fullcap=512, guards=2))
    for filename in ('runtime.c', 'startup.S', 'replay.ld'):
        shutil.copyfile(base.INTEGRATION / filename, prepared / filename)
    provenance = dict(cases=cases, vlen=1024, nr_lanes=4,
        scope='Original-source failing tuple single plus explicit start0 control, NOT prefix closure',
        source_origin=str(ARCHIVED), source_sha256=base.sha(ARCHIVED / 'scenario.c'),
        original_linux_elf_sha256=base.sha(ARCHIVED / 'original_linux.elf'),
        source_diff_sha256=base.sha(OUT / 'source.diff'),
        full_original_rng_setup_oracle_guards_statistics=True,
        files={str(path.relative_to(prepared)): base.sha(path) for path in prepared.rglob('*') if path.is_file()})
    base.save(prepared / 'provenance.json', provenance)
    base.HERE = OUT
    soc, spike = base.build(prepared, provenance, 'soc'), base.build(prepared, provenance, 'spike')
    finish(soc, spike, specs)


def finish(soc, spike, specs):
    import prepare_stall_prefix2 as reference_helper
    reference_helper.BOUND = 1
    reference = OUT / 'reference_commit'
    reference.mkdir(exist_ok=True)
    for spec in specs:
        name = spec['name']
        elf = Path(soc[name]['path'])
        spec['soc_routine'] = instructions(elf, name+'_op_20')
        original = archived_window(ARCHIVED / 'original_linux.elf', spec['soc_routine'])
        assert len(original) == len(spec['soc_routine']) == 13
        assert [r['insn'] for r in original] == [r['insn'] for r in spec['soc_routine']]
        assert [r['insn'] for r in instructions(Path(spike[name]['path']), name+'_op_20')] == [r['insn'] for r in original]
        for key, symbol_name in (('input_address','input'), ('index_address','indices16'),
                                 ('output_address','output'), ('predicate_address','predicate')):
            spec[key] = symbol(elf, symbol_name, OBJDUMP)[0]
        spec['soc_elf_sha256'] = soc[name]['sha256']
        # Spike executes both full original scalar oracles; no DUT acceptance implication.
        log_address = symbol(Path(spike[name]['path']), 'replay_log', OBJDUMP)[0]
        debug = reference / (name + '.cmd')
        debug.write_text('rs 500000\nstr %x\nquit\n' % log_address)
        commits = reference / (name + '.commits.log')
        command = [str(SPIKE), '-d', '--debug-cmd='+str(debug), '--isa=rv64gcv_zvl1024b',
                   '-m2', '--log-commits', '--log='+str(commits), spike[name]['path']]
        log = reference / (name + '.log')
        if not commits.exists():
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            log.write_text(result.stdout + result.stderr)
            assert result.returncode == 0
        measured = reference_helper.reference_trace(commits, Path(spike[name]['path']), name,
                    json.loads((OUT / (name + '.expected.json')).read_text()))
        console = measured.pop('reconstructed_runtime_console')
        runtime = reference / (name + '.runtime.log')
        runtime.write_text(console)
        assert all(marker in console for marker in spike[name]['pass_markers'])
        assert 'RVV_PERMUTE_DETAIL' not in console
        spec['spike'] = dict(command=command, log_sha256=base.sha(log),
                            commit_sha256=base.sha(commits), **measured)
    base.save(OUT / 'plan.json', dict(image=str(IMAGE), image_sha256=base.sha(IMAGE / 'image.json'),
        unit='ara-gather-focused-candidate04-01.service', output=str(OUT / 'vcs_candidate04_01'),
        jobs=2, timeout_s=180, retries=0, bounded_window_ns=[0,90000], force=False,
        hypothesis='AluA origin128 vs MASKU scan0: scan0->source128, scan128->source256',
        cases=specs, original_stopped_tuple=None, prefix_closed=False))
    base.save(OUT / 'prepared_pins.json', {str(path): base.sha(path) for path in OUT.rglob('*') if path.is_file()})
    print('PREPARED_TWO_SPIKE_PASS_NO_DUT', OUT)


if __name__ == '__main__':
    if sys.argv[1:] == ['--finish-existing-build']:
        finish(json.loads((OUT / 'soc01/programs.json').read_text())['programs'],
               json.loads((OUT / 'spike01/programs.json').read_text())['programs'],
               [dict(name=name, tuple=[0,20,0,4,0,1], actual_vstart=128 if i == 0 else 0,
                     control_override=bool(i), fullcap=512, guards=2) for i,name in enumerate(NAMES)])
    else:
        main()
