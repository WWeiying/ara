#!/usr/bin/env python3
"""Read pinned evidence and emit a plan only. No build, runner, or simulator call."""
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REF = HERE/'reference01'
FROZEN = Path('/home/wangwy/fpga_runs/current_board_memory_candidate02/frozen')
OLD = Path('/home/wangwy/fpga_runs/current_board_integration_final04/frozen')
IMAGE = FROZEN.parent/'campaign/image'
EXPECTED = {
    'hardware/src/vlsu/addrgen.sv': '470c6c92d26cd2e540562302788f58d8d85ae6f147886fb949668e7728be41da',
    'hardware/src/vlsu/vldu.sv': '4e46a4733530b15edb05bbaded651899511af930e2caffe77b7482528c4fc8ab',
    'hardware/src/ara_sequencer.sv': 'bf5d5a9be860340ca7a6f8d8c636da67cf9650f7b7b72d1123ce983e8eea5655',
}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def read(p):
    return json.loads(p.read_text())


def main():
    out = HERE/'vcs_plan01'
    if out.exists():
        raise ValueError('Refuse overwrite of existing plan')
    pin = read(REF/'input_pins.json')
    for p,h in pin.items():
        if sha(p) != h:
            raise ValueError('Reference input drift: '+p)
    snapshots = [read(p/'snapshot.json') for p in (OLD,FROZEN)]
    for directory,ledger in zip((OLD,FROZEN),snapshots):
        if len(ledger['files']) != 539:
            raise ValueError('Not 539 inputs')
        for name,digest in ledger['files'].items():
            if sha(directory/'sources'/name) != digest:
                raise ValueError('Frozen file drift: '+str(directory/name))
    a,b = snapshots
    if set(a['files']) != set(b['files']):
        raise ValueError('Source membership differs')
    delta = sorted(n for n in a['files'] if a['files'][n] != b['files'][n])
    if delta != sorted([*EXPECTED,'frozen.filelist','hardware/bender']):
        raise ValueError('Unexpected delta: '+str(delta))
    for n,h in EXPECTED.items():
        if b['files'][n] != h:
            raise ValueError('Candidate hash differs: '+n)
    for n in ('frozen.filelist','hardware/bender'):
        texts = [(p/'sources'/n).read_text().replace(str(p/'sources'),'@ROOT@') for p in (OLD,FROZEN)]
        if texts[0] != texts[1]:
            raise ValueError('Non-relocation metadata change')
    status = read(REF/'status.json')
    if status['status'] != 'HOST_SPIKE_PASS_NOT_DUT':
        raise ValueError('Reference is not PASS')
    for backend,digest in status['elf_sha256'].items():
        if sha(REF/(backend+'.elf')) != digest:
            raise ValueError('ELF drift')
    symbols = read(REF/'soc.symbols.json')
    if 'tohost' in symbols:
        raise ValueError('Not a SoC symbol set')
    previous = read(HERE.parent/'sv39_candidate01_acceptance01/analysis.json')['results']
    reference = read(HERE.parent/'sv39_reference02/status.json')['spike']
    calibrations = []
    for name,measurement in previous.items():
        ratio = status['commits']/reference[name]['retired']
        calibrations.append(dict(name=name,prior_wall_s=measurement['runner']['elapsed_s'],
            prior_last_cycle=measurement['last_cycle'],prior_reference_commits=reference[name]['retired'],
            estimated_cycles=round(measurement['last_cycle']*ratio),
            estimated_wall_s=round(measurement['runner']['elapsed_s']*ratio,3)))
    cpus = [x['prior_last_cycle']/x['prior_reference_commits'] for x in calibrations]
    wall = [x['prior_wall_s']/x['prior_reference_commits'] for x in calibrations]
    milestones = []
    prior = 0
    for p in status['checkpoints']:
        n=p['id']; commit=p['commit']
        milestones.append(dict(**p,reference_delta=commit-prior,
            estimated_cycle_range=[round(commit*min(cpus)),round(commit*max(cpus))],
            estimated_wall_s_range=[round(commit*min(wall),1),round(commit*max(wall),1)],
            case_counter_address=hex(symbols['mx_case_checks']+8*n),
            case_counter_value=status['case_checks'][n],
            marker_address=hex(symbols['mx_marker']+8*n),
            trap_count_address=hex(symbols['mx_count']+8*n)))
        prior=commit
    sources = read(REF/'linux_provenance.json')
    excerpts = ['# Read-Only Original Source Excerpts', '',
                'Original Linux source is retained and hash verified, not run bare metal.',
                'Fixture C/S is a semantic adapter, not byte-identical original source.', '']
    for case in sources['cases']:
        d=Path(case['source_directory'])
        excerpts += ['## '+case['name'], '', str(d), '']
        for name in ('scenario.S','scenario.c'):
            path=d/name; lines=path.read_text().splitlines()
            excerpts += [f'{name} SHA256 `{sha(path)}`', '']
            if name.endswith('.S'):
                chosen=list(range(len(lines)))
            else:
                terms=('Changing completed','Keep the saved PC','state->vstart!=',
                       'stride=','target=mapping','mask[i]=','wanted=','scenario==0 && i>=4')
                chosen=sorted({j for i,line in enumerate(lines) if any(t in line for t in terms)
                               for j in range(max(0,i-1),min(len(lines),i+4))})
            excerpts += ['```text']+[f'{i+1:4d}: {lines[i]}' for i in chosen]+['```','']
    plan = dict(status='PLAN_ONLY_NOT_IMAGE_PREFLIGHT_NOT_LAUNCHED',single_elf=True,subcases=8,
        image=str(IMAGE),frozen=str(FROZEN),frozen_snapshot_sha256=sha(FROZEN/'snapshot.json'),
        frozen_files_verified=539,reference_input_pins_verified=len(pin),semantic_delta=EXPECTED,
        soc_elf=str(REF/'soc.elf'),soc_elf_sha256=status['elf_sha256']['soc'],
        symbols_sha256=sha(REF/'soc.symbols.json'),reference_status_sha256=sha(REF/'status.json'),
        max_parallel=1,timeout_wall_s=1200,cycle_diagnostic_ceiling=1350000,
        bound_enforcement='Wall timeout supported by sealed runner; cycle/stage observer not implemented here',
        required_gates=['Tesla final sequencer 7 local cases PASS','Parent combined image build PASS',
                        'Parent same-image 3 Sv39 and 10 smoke completion reviewed',
                        'No overlap with parent pipeline','Fresh user authorization',
                        'Separate image/ELF/runner preflight and successor CSV observer'],
        calibrations=calibrations,milestones=milestones,
        soc_symbols={n:hex(a) for n,a in symbols.items() if n.startswith('mx_') or n in ('check','replay_exit','replay_mismatch')},
        success=dict(checks=6227,errors=0,unexpected=0,case_checks=status['case_checks'],
                     complete_magic='0x6d78737633390008',uart='MX_SV39_PASS',ctrl_return_code=0),
        VCS_started=False,RTL_build=False,helpers_modified=False)
    out.mkdir()
    (out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    (out/'ORIGINAL_EXCERPTS.md').write_text('\n'.join(excerpts)+'\n')
    print(json.dumps(dict(status=plan['status'],output=str(out),calibrations=calibrations),indent=2))


if __name__ == '__main__':
    main()
