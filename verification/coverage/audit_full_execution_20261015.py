#!/usr/bin/env python3
"""Read-only execution audit; no runner imports, simulation, or large-log hashes.

Exit 0 means all 798 execution/identity chains are supported, NOT all tests pass.
Logs are bounded head/tail samples, not a fresh semantic or full-log audit.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / 'verification/out/gather-war-offline-admitted798-v2-parent-20261008-01/elf-ledger-dedup.json'
LEDGER_SHA = 'b2820b1db622fe81608afca6c0314cde25995e2fdc604ca0fc3a22a5565ddcd9'
RECOVERY = ROOT / 'verification/out/fence-t-u-padding-linked-agent-727-20261006-01/review.json'
RECOVERY_SHA = 'f43c5b5374b60779359772babbb88359f9640ec410d8817b3951f61754857292'
HASHES, METADATA, LOGS = {}, {}, {}


def read(path):
    path = Path(path)
    if path not in METADATA:
        METADATA[path] = json.loads(path.read_text())
    return METADATA[path]


def sha(path):
    path = Path(path).resolve(strict=True)
    if path not in HASHES:
        h = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                h.update(chunk)
        HASHES[path] = h.hexdigest()
    return HASHES[path]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def pins(mapping):
    issues = []
    for path, expected in mapping.items():
        try:
            require(sha(path) == expected, 'hash mismatch')
        except (OSError, ValueError) as error:
            issues.append(f'{path}: {error}')
    return issues


def plus(command, key):
    values = [a.split('=', 1)[1] for a in command if a.startswith(key + '=')]
    require(len(values) == 1, f'missing/ambiguous {key}')
    return values[0]


def log_sample(path):
    path = Path(path)
    if path not in LOGS:
        size = path.stat().st_size
        with path.open('rb') as stream:
            head = stream.read(32768).decode(errors='replace')
            stream.seek(max(0, size - 32768))
            tail = stream.read(32768).decode(errors='replace')
        command = next((line[9:] for line in head.splitlines() if line.startswith('Command: ')), '')
        LOGS[path] = dict(path=str(path), bytes=size, sample_limit_per_end=32768,
                          command=shlex.split(command),
                          vcs_started='Chronologic VCS simulator' in head,
                          loaded_elf=re.findall(r'Loading ELF file\s+(\S+)', head),
                          finished='$finish' in tail,
                          simulation_report='S i m u l a t i o n' in tail,
                          tail_excerpt=tail[-1600:])
    return LOGS[path]


def bind_log(row, path, simv, expected, case_dir):
    evidence = log_sample(path)
    row['log'] = evidence
    require(evidence['vcs_started'], 'MISSING_EVIDENCE: no VCS startup in log')
    cmd = evidence['command']
    require(cmd and cmd[0] == simv, 'WRONG_IMAGE: log command image differs')
    elf = Path(plus(cmd, '+PRELOAD'))
    require(elf.is_relative_to(case_dir), 'WRONG_ELF: preload outside fresh case')
    require(sha(elf) == expected, 'WRONG_ELF: actual preload hash differs')
    row['actual_elf'] = str(elf)
    row['actual_elf_sha256'] = sha(elf)
    require(str(elf) in evidence['loaded_elf'], 'MISSING_EVIDENCE: ELF loading line absent/differs')
    row['execution_confirmed'] = True
    return cmd


def audit(root):
    core = root / 'full-regression-core-20261015-01'
    ext = root / 'extensions'
    plan, freeze = read(core / 'plan.json'), read(root / 'freeze.json')
    ledger = read(LEDGER)
    require(sha(LEDGER) == LEDGER_SHA, 'ledger pin mismatch')
    require(ledger['ledger_members'] == len(ledger['members']) == 798, '798 ledger required')
    require(len(plan['cases']) == 600, '600 core cases required')
    image, simv = freeze['image'], freeze['simv']
    build = Path(simv).parent.parent
    global_issues = []
    for label, ok in (
        ('core image vs freeze', plan['image'] == image),
        ('build image vs freeze', read(build / 'build-image.json') == image),
        ('build PASS/current image', read(build / 'build-status.json').get('status') == 'PASS'
         and read(build / 'build-status.json').get('image') == image),
        ('extension image vs freeze', read(ext / 'complete.json').get('image') == image),
    ):
        if not ok:
            global_issues.append(label)
    # Resolve symlink aliases so shared libraries and source files are hashed once.
    source = read(build / 'build-source-pins.json')
    manifest = read(Path(simv).parent / 'vcs_source_manifest.json')
    source.update({item['path']: item['sha256'] for item in manifest['files']})
    global_issues += pins(dict(source, **image, **plan['wrapper_image']))
    actual_libraries = {str(p) for p in Path(simv + '.daidir').rglob('*.so') if p.is_file()}
    require(actual_libraries == {p for p in image if p.endswith('.so')}, 'image library membership differs')
    wrapper_config = read(core / 'inputs/coverage-wrapper.json')
    require(wrapper_config['simv'] == simv and wrapper_config['image'] == image, 'wrapper binding differs')
    outcomes = {o['name']: o for o in read(core / 'all-outcomes.json')}
    require(len(outcomes) == 600, '600 unique aggregate outcomes required')
    rows = []
    for index in range(798):
        member = ledger['members'][index]
        row = dict(index=index, group='core' if index < 600 else 'extensions',
                   original_vdb=member['vdb'], supported=False, issues=[])
        rows.append(row)
        try:
            if index < 600:
                c = plan['cases'][index]
                name, expected = c['name'], c['elf_sha256']
                row.update(name=name, kind=c['kind'])
                require(name.startswith(f'c{index:04d}-') and f'c{index:04d}-' in member['vdb'], 'ledger order differs')
                require(set(member['ELF_candidates'].values()) == {expected}, 'WRONG_ELF: ledger identity differs')
                require(sha(c['frozen_elf']) == expected, 'WRONG_ELF: frozen ELF differs')
                out = read(core / 'outcomes' / (name + '.json'))
                require(out == outcomes[name], 'outcome vs aggregate differs')
                row.update(verdict=out['status'], runner_returncode=out.get('returncode'))
                require(out.get('reused') is False and out.get('elf_sha256') == expected, 'outcome identity/reuse differs')
                target = core / 'results' / name
                if c['kind'] in ('uvm', 'axpy'):
                    report = read(target / 'uvm_result.json')
                    require(report['sim_image_sha256'] == image and report['elf_sha256'] == expected, 'UVM identity differs')
                    cmd = bind_log(row, target / 'work/run.vcs.log', simv, expected, target)
                    rc = out.get('simulator_returncode')
                    origin = 'outcome.simulator_returncode (timeout wrapper)'
                    if rc is None:
                        helper = ROOT / 'verification/uvm/run_real_dut_case.sh'
                        require(sha(helper) == plan['files'][str(helper)], 'UVM helper drift')
                        require(out.get('returncode') == 0 and report.get('status') == 'PASS'
                                and (target / 'RUN_SHA256SUMS').is_file(),
                                'MISSING_EVIDENCE: cannot infer shell simulator exit')
                        rc, origin = 0, 'INFERRED: pinned set-e shell reached post-simulation hashes; no standalone numeric simulator receipt'
                    row.update(returncode=rc, exit_origin=origin)
                else:
                    summary = read(target / 'summary.json')
                    require(len(summary) == 1, 'ambiguous summary')
                    s = summary[0]
                    artifact = Path(s['artifact_dir'])
                    require(artifact.is_relative_to(target), 'artifact outside current case')
                    receipt = read(artifact / 'inputs.json')
                    require(receipt['binary']['sha256'] == expected, 'inputs ELF identity differs')
                    require(receipt['simv']['image_sha256'] == plan['wrapper_image'], 'inputs wrapper image differs')
                    command_files = [p for p in (artifact / 'coverage.command.json',
                                                 artifact / 'work/coverage.command.json') if p.is_file()]
                    require(len(command_files) == 1, 'missing/ambiguous actual command')
                    command = read(command_files[0])
                    cwd = Path(command['cwd'])
                    cmd = bind_log(row, cwd / 'run.vcs.log', simv, expected, target)
                    require(cmd == command['command'], 'command metadata vs log differs')
                    rc_key = 'rtl_returncode' if c['kind'] in ('random', 'replay') else 'returncode'
                    row.update(returncode=s.get(rc_key), exit_origin=f'summary[0].{rc_key}')
                small = {p: h for p, h in out.get('files', {}).items()
                         if Path(p).name in ('summary.json', 'inputs.json', 'coverage.command.json', 'uvm_result.json')}
                require(not pins(small), 'MISSING_EVIDENCE: core small metadata pin mismatch')
                require(type(row['returncode']) is int, 'MISSING_EVIDENCE: numeric simulator exit absent')
            else:
                case = ext / f'e{index:04d}'
                c, result, receipt = read(case / 'plan.json'), read(case / 'result.json'), read(case / 'simulation-exit.json')
                row.update(name=f'e{index:04d}', kind='extension', verdict=result['status'],
                           returncode=receipt.get('returncode'), exit_origin='simulation-exit.json',
                           executed=receipt.get('executed'), pid=receipt.get('pid'),
                           timed_out=receipt.get('timed_out'), cancelled=receipt.get('cancelled'),
                           receipt=str(case / 'simulation-exit.json'))
                require(receipt.get('executed') is True, 'NOT_RUN: receipt executed is not true')
                require(type(receipt.get('returncode')) is int and type(receipt.get('pid')) is int
                        and receipt['finished'] >= receipt['started'], 'MISSING_EVIDENCE: invalid wait receipt')
                expected = c['elf_sha256']
                old = c['original_command']
                original_elf = plus(old, '+PRELOAD')
                require(c['index'] == index and c['original_vdb'] == member['vdb'], 'ledger member differs')
                require(old[old.index('-cm_dir') + 1] == member['vdb'], 'historical command VDB differs')
                if index == 727:
                    recovery = read(RECOVERY)
                    require(sha(RECOVERY) == RECOVERY_SHA, '727 recovery pin differs')
                    require(recovery['run']['argv'][4:] == old and recovery['ELF_sha256'] == expected
                            and recovery['pins'][original_elf] == expected
                            and original_elf not in member['ELF_candidates'], '727 recovery chain differs')
                    row['identity_exception'] = dict(reason='Old ledger 727 ELF candidates are unrelated; recovered linked review, not exact old-ledger ELF match',
                        review=str(RECOVERY), review_sha256=RECOVERY_SHA,
                        old_ledger_candidates=member['ELF_candidates'], recovered_elf=original_elf,
                        recovered_sha256=expected)
                else:
                    require(member['ELF_candidates'].get(original_elf) == expected, 'WRONG_ELF: ledger preload differs')
                    archived = read(c['command_source'])
                    require(archived.get('command') == old, 'historical command source differs')
                require(sha(original_elf) == expected, 'WRONG_ELF: historical ELF differs')
                # Small command/Tcl pins only; never hash Spike references or logs.
                small = {p: h for p, h in c['pins'].items() if Path(p).suffix in ('.json', '.tcl', '.elf')}
                require(not pins(small), 'input pin mismatch')
                require(receipt['command'] == c['command'] == result['command'], 'actual vs planned command differs')
                require(receipt['cwd'] == c['work'], 'receipt cwd differs')
                require(result['executed'] is True and result['returncode'] == receipt['returncode'], 'result vs receipt differs')
                cmd = bind_log(row, case / 'work/run.vcs.log', simv, expected, case)
                require(cmd == receipt['command'], 'receipt vs log command differs')
            row['supported'] = not global_issues
            if global_issues:
                row['issues'].append('shared image/source evidence failed; see shared-evidence.json')
        except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
            row['issues'].append(str(error))
    if global_issues:
        for row in rows:
            row['execution_confirmed'] = False
    return rows, dict(image=image, source_files=len(source), image_files=len(image),
                      issues=global_issues, ledger_sha256=sha(LEDGER),
                      build_status=str(build / 'build-status.json'), source_manifest=manifest['filelist'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT / 'verification/out/full-regression-20261015-01')
    parser.add_argument('--output', type=Path, default=ROOT / 'verification/out/full-regression-failure-review-20261015-01/execution')
    args = parser.parse_args()
    rows, shared = audit(args.root.resolve())
    unsupported = [r for r in rows if not r['supported']]
    summary = dict(audited_at=datetime.now(timezone.utc).isoformat(), root=str(args.root.resolve()),
        total=len(rows), executed_with_matching_elf_and_image=sum(r.get('execution_confirmed', False) for r in rows),
        supported=sum(r['supported'] for r in rows), unsupported=len(unsupported),
        groups={g: dict(total=len(rs), supported=sum(r['supported'] for r in rs),
                        exits=dict(Counter(str(r.get('returncode')) for r in rs)),
                        verdicts=dict(Counter(r.get('verdict', 'UNKNOWN') for r in rs)))
                for g in ('core', 'extensions') for rs in [[r for r in rows if r['group'] == g]]},
        direct_numeric_exit_count=sum(type(r.get('returncode')) is int and not r.get('exit_origin', '').startswith('INFERRED') for r in rows),
        inferred_zero_exit_indices=[r['index'] for r in rows if r.get('exit_origin', '').startswith('INFERRED')],
        not_run=[r['index'] for r in rows if r.get('executed') is False],
        wrong_elf=[r['index'] for r in rows if any('WRONG_ELF' in s for s in r['issues'])],
        missing_or_conflicting_evidence=[r['index'] for r in unsupported],
        identity_exceptions=[r['index'] for r in rows if 'identity_exception' in r],
        unique_files_hashed=len(HASHES), logs_hashed=0, logs_sampled=len(LOGS),
        scope='Execution and identity only; not a new functional PASS, full-log veto, coverage signoff, or proof against malicious artifact fabrication.')
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in [('summary', summary), ('cases', rows), ('unsupported', unsupported),
                        ('shared-evidence', shared), ('identity-exceptions', [r for r in rows if 'identity_exception' in r]),
                        ('hash-manifest', {str(p): h for p, h in HASHES.items()})]:
        (args.output / (name + '.json')).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    report = ['# Execution Audit 2026-10-15', '',
              f"Executed with matching ELF/image: {summary['executed_with_matching_elf_and_image']}/798.",
              f"Supported execution/identity AND exit chains: {summary['supported']}/798.",
              f"Direct numeric exits: {summary['direct_numeric_exit_count']}; inferred shell exit=0: {len(summary['inferred_zero_exit_indices'])}.",
              'Ledger index 727 is a separately recorded recovered identity, not an exact old-ledger ELF match.',
              'A nonzero exit, TIMEOUT, FAIL or CHECKER_REQUIRED still counts as executed when the chain is supported.',
              'No simulation, RTL edits, giant-log hashes, or functional reclassification. Log samples: 32 KiB per end.', '',
              '## Missing / Wrong / Not Run', '']
    report += [f"- {r['index']} {r.get('name', '')}: {'; '.join(r['issues'])}" for r in unsupported] or ['None.']
    report += ['', 'See cases.json for every exit, identity, verdict and bounded log evidence; shared-evidence.json for image/source validation.',
               'Inferred UVM exits are not standalone numeric receipts. No full-log semantic acceptance is claimed.']
    (args.output / 'README.md').write_text('\n'.join(report) + '\n')
    print(json.dumps(summary, indent=2))
    return int(bool(unsupported))


if __name__ == '__main__':
    raise SystemExit(main())
