#!/usr/bin/env python3
"""Prepare identical-ELF candidate commands only. No simulator launch entrypoint."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import final04_baseline as baseline
import sv39_adapter as ref
sys.path.insert(0,str(ref.BASE))
import run as checked

OLD = Path('/home/wangwy/fpga_runs/current_board_integration_final04/frozen')
CANDIDATE = Path('/home/wangwy/fpga_runs/current_board_masked_candidate01/frozen')
IMAGE = CANDIDATE.parent/'image'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    args = p.parse_args()
    out = ref.inside(args.out)
    ref.require(not out.exists(),'Fresh staging directory required')
    baseline.check_reference()
    before,after = checked.sealed(OLD),checked.sealed(CANDIDATE)
    a,b = [json.loads((root/'snapshot.json').read_text()) for root in (OLD,CANDIDATE)]
    ref.require(len(a['files']) == len(b['files']) == 539 and
                set(a['files']) == set(b['files']), 'Frozen source membership changed')
    raw = [n for n in a['files'] if a['files'][n] != b['files'][n]]
    ref.require(set(raw) == {'frozen.filelist','hardware/bender','hardware/src/vlsu/addrgen.sv'},
                'Unexpected source delta')
    for n in ('frozen.filelist','hardware/bender'):
        ref.require((before/n).read_text().replace(str(before),'@SOURCE_ROOT@') ==
                    (after/n).read_text().replace(str(after),'@SOURCE_ROOT@'),
                    'Adapter/filelist changes exceed path relocation')
    ref.require(b['files']['hardware/src/vlsu/addrgen.sv'] ==
                '470c6c92d26cd2e540562302788f58d8d85ae6f147886fb949668e7728be41da',
                'Candidate source identity changed')
    programs = json.loads((baseline.REFERENCE/'soc/programs.json').read_text())
    commands = {}
    future = out.parent/'sv39_candidate01_acceptance01'
    for name in ref.NAMES:
        commands[name] = [str(baseline.PYTHON),'-B',str(baseline.RUNNER),'run',
            '--image',str(IMAGE),'--programs',str(baseline.REFERENCE/'soc'),
            '--case',name,'--jobs','1','--timeout','600','--execute','--out',str(future/name)]
    out.mkdir()
    ref.save(out/'plan.json',dict(status='STAGED_ONLY_WAIT_PARENT_LOCAL_AND_BUILD_PASS',
        no_launch=True,candidate_build_service='ara-board-masked-candidate-build02',
        first_failed_build_not_accepted=True,
        old_snapshot_sha256=ref.sha(OLD/'snapshot.json'),
        candidate_snapshot_sha256=ref.sha(CANDIDATE/'snapshot.json'),
        checked_frozen_inputs=539,raw_changed=raw,
        path_only_changes=['frozen.filelist','hardware/bender'],
        semantic_changed=['hardware/src/vlsu/addrgen.sv'],
        candidate_addrgen_sha256=b['files']['hardware/src/vlsu/addrgen.sv'],
        same_elf_bindings=programs['programs'],commands_NOT_EXECUTED=commands,
        max_parallel=3,timeout_per_case_s=600,
        before_launch_requirements=['Explicit parent confirmation: local tests PASS and build02 PASS',
            'Verify completed candidate image.json binds this exact snapshot',
            'Run sealed runner dry-run to validate image libraries/config/source manifest and ELF pins',
            'Execute each singleton runner independently; do not cancel sibling cases on failure'],
        pass_contract='All three strict architectural software oracles and independent trap/retry checks pass',
        baseline_results_are_not_candidate_results=True,
        script_sha256=ref.sha(Path(__file__))))
    print(json.dumps(dict(status='STAGED_NOT_LAUNCHED',output=str(out),
                         semantic_changed=['hardware/src/vlsu/addrgen.sv']),indent=2))


if __name__ == '__main__':
    main()
