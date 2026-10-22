#!/usr/bin/env python3
"""One current-image e0650 successor; add missing vector evidence, never retry.

No build/RTL edit, old-manifest impersonation, historical result inheritance,
or PASS from simulator exit. Final custom-native approval is independent.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import signal
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'verification'))
import replay_historical_extensions_20261015 as prior
import gap65_late_fault_checks as checks
import gap65_observer_echo as echo
import run_gap65_late_fault_observed as observed
from ara_verify.artifacts import simulation_image
from ara_verify.contract import check_contract_log
from ara_verify.trace import validate_trace
from run_vcs_dve_batch import valid_vdb

SOURCE = ROOT / 'verification/out/full-regression-20261015-01/extensions/e0650'
OUTPUT = ROOT / 'verification/out/pending94-e0650-replay-20261016-01'
HOST = ROOT / 'verification/out/gap65-late-fault-preflight-20261004-04'
HASHES = {}


def sha(path):
    path = Path(path).resolve(strict=True)
    stat = path.stat()
    identity = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    if path not in HASHES or HASHES[path][0] != identity:
        h = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1048576), b''):
                h.update(chunk)
        HASHES[path] = (identity, h.hexdigest())
    return HASHES[path][1]


def verify(pins):
    for path, expected in pins.items():
        prior.require(sha(path) == expected, 'input pin drift: ' + path)


def prepare(output):
    prior.require(output == OUTPUT and not output.exists(), 'exact fresh successor required')
    original = prior.read(SOURCE / 'plan.json')
    actual = prior.read(SOURCE / 'simulation-exit.json')
    freeze = prior.read(SOURCE.parent.parent / 'freeze.json')
    prior.require(actual['command'] == original['command'] and actual['executed'] is True
                  and type(actual['returncode']) is int, 'original actual command not bound')
    prior.require(not any(a.startswith('+VECTOR_TRACE=') for a in actual['command']), 'missing-trace premise changed')
    verify(original['pins'])
    simv = Path(actual['command'][0])
    prior.require(str(simv) == freeze['simv'], 'not the approved current image')
    image = simulation_image(simv)
    prior.require(image == freeze['image'], 'current image membership/hash drift')
    # Current manifest only; never substitute the original frozen admission.
    manifest_path = simv.parent / 'vcs_source_manifest.json'
    manifest = prior.read(manifest_path)
    verify({r['path']: r['sha256'] for r in manifest['files']})
    tcl_source = Path(prior.option(actual['command'], '-do'))
    tcl = tcl_source.read_text()
    prior.require(tcl == observed.OBSERVER.read_text(), 'original/frozen observer logic differs')
    prior.require('open gap65-observer.tsv {WRONLY CREAT EXCL}' in tcl
                  and not prior.ABS_TCL.search(tcl) and '../' not in tcl
                  and not any(s in tcl for s in ('force ', 'deposit ', 'exec ', 'source ')),
                  'unclassified Tcl filesystem/HDL effects')
    elf_source = Path(prior.plus(actual['command'], '+PRELOAD'))
    prior.require(sha(elf_source) == original['elf_sha256'], 'original executed ELF changed')
    output.mkdir(parents=True)
    work, inputs = output / 'work', output / 'inputs'
    work.mkdir()
    inputs.mkdir()
    private_elf, private_tcl = output / 'input.elf', inputs / 'gap65_late_fault.tcl'
    shutil.copyfile(elf_source, private_elf)
    shutil.copyfile(tcl_source, private_tcl)
    command = prior.rewrite(actual['command'], simv, work, private_elf, private_tcl)
    command.append('+VECTOR_TRACE=' + str(work / 'vector_trace.csv'))
    outputs = ('-l', '-cm_dir', '+COMMIT_TRACE', '+VECTOR_TRACE', '+PRELOAD', '-do')
    for key in outputs:
        value = prior.plus(command, key) if key.startswith('+') else prior.option(command, key)
        prior.require(Path(value).is_relative_to(output), 'unremapped output/input path: ' + key)
    # Only approved instrumentation/path changes relative to actual command.
    def semantic(argv):
        skip = {'-l', '-cm_dir', '-do'}
        result, i = [], 1
        while i < len(argv):
            if argv[i] in skip:
                i += 2
            elif argv[i].split('=')[0] in ('+PRELOAD', '+COMMIT_TRACE', '+VECTOR_TRACE'):
                i += 1
            else:
                result.append(argv[i])
                i += 1
        return result
    prior.require(semantic(command) == semantic(actual['command']), 'unapproved simulator semantic change')
    files = {str(p): sha(p) for p in (SOURCE / 'plan.json', SOURCE / 'simulation-exit.json',
        SOURCE.parent.parent / 'freeze.json', manifest_path, elf_source, tcl_source,
        private_elf, private_tcl, Path(__file__), Path(checks.__file__), Path(observed.__file__),
        Path(echo.__file__), HOST / 'elf-proof.json', HOST / 'dut.metadata.log',
        ROOT / 'apps/qbs_gap65_late_fault/main.c', ROOT / 'apps/qbs_gap65_late_fault/execute.S',
        ROOT / 'apps/qbs_gap65_late_fault/entry.S')}
    plan = dict(index=650, name='e0650', directory=str(output), work=str(work),
                command=command, original_command=actual['command'], timeout_s=600,
                command_source=original['command_source'],
                elf_sha256=original['elf_sha256'], image=image, pins=files,
                vdb=str(work / 'code.vdb'), observer=str(private_tcl),
                observer_sha256=sha(private_tcl), original_observer_sha256=sha(tcl_source),
                source_manifest=str(manifest_path), original_evidence=str(SOURCE),
                approved_changes=['private output/input paths', '+VECTOR_TRACE', 'host wall cap 600s'],
                no_rtl_edit=True, no_build=True, host_vcs=True, retries=0,
                original_admission_reused=False, semantic_checker_required=True)
    prior.save(output / 'image-pins.json', image)
    prior.save(output / 'plan.json', plan)
    return plan


def base_check(plan):
    output, work = Path(plan['directory']), Path(plan['work'])
    receipt = prior.read(output / 'simulation-exit.json')
    prior.require(receipt['executed'] is True and type(receipt['returncode']) is int
        and receipt['returncode'] == 0 and receipt['timed_out'] is False
        and receipt['cancelled'] is False and type(receipt['pid']) is int
        and type(receipt['elapsed_s']) in (int, float) and receipt['finished'] >= receipt['started']
        and receipt['command'] == plan['command'] and receipt['cwd'] == plan['work'], 'actual wait/identity failed')
    verify(plan['pins'])
    proof = prior.read(HOST / 'elf-proof.json')
    prior.require(proof['elf_sha256'] == plan['elf_sha256'], 'host ELF proof differs')
    logs = {}
    for path in (output / 'console.log', work / 'run.vcs.log'):
        raw = path.read_text(errors='strict')
        normalized, normalization = echo.normalize(raw, Path(plan['observer']).read_text())
        checks.check_runtime_log(normalized, proof)
        prior.require(not prior.RAW_FAIL.search(normalized), 'raw simulator/firmware error')
        prior.require(not check_contract_log(path), 'protocol log check failed')
        logs[str(path)] = normalization
    samples = observed.observer_samples((work / 'gap65-observer.tsv').read_text())
    trace = validate_trace(work / 'commit_trace.csv')
    prior.require((work / 'vector_trace.csv').stat().st_size > 0, 'missing actual vector trace')
    vdb_files = valid_vdb(Path(plan['vdb']), checks.NAME, plan['command'][0])
    # Recompute the image once at completion, not once per small input/log.
    prior.require(simulation_image(Path(plan['command'][0])) == plan['image'], 'image changed during execution')
    return dict(status='CHECKER_REQUIRED', runtime49_checks=True, observer_samples=samples,
                trace=trace, echo_normalization=logs, vdb=plan['vdb'], vdb_files=vdb_files,
                reason='Await independent bit-exact custom-native/VRF/CSR/trap/guards semantic approval',
                original_evidence_unchanged=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--run-prepared', action='store_true')
    args = parser.parse_args()
    if args.run_prepared:
        plan = prior.read(OUTPUT / 'plan.json')
        prior.require(not (OUTPUT / 'simulation-exit.json').exists(), 'no retry')
        verify(plan['pins'])
        prior.require(simulation_image(Path(plan['command'][0])) == plan['image'], 'prepared image drift')
    else:
        plan = prepare(OUTPUT)
    if args.prepare_only:
        print(json.dumps(dict(status='PREPARED_NOT_EXECUTED', plan=str(OUTPUT / 'plan.json'), sha256=sha(OUTPUT / 'plan.json'))))
        return 0
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: prior.STOP.set())
    prior.save(OUTPUT / 'progress.json', dict(status='RUNNING', plan=str(OUTPUT / 'plan.json')))
    receipt = prior.child(plan['command'], Path(plan['work']), OUTPUT / 'console.log', 600,
                          OUTPUT / 'simulation-exit.json')
    try:
        result = base_check(plan)
    except Exception as error:
        result = dict(status='FAIL_OR_MISSING_EVIDENCE', reason=f'{type(error).__name__}: {error}')
    result.update(plan=str(OUTPUT / 'plan.json'), simulation_receipt=str(OUTPUT / 'simulation-exit.json'),
                  actual_returncode=receipt['returncode'], tests_rerun=1, aggregate_admitted=False)
    prior.save(OUTPUT / 'result.json', result)
    prior.save(OUTPUT / 'progress.json', dict(status=result['status']))
    prior.save(OUTPUT / 'artifact-hashes.json', {str(p): sha(p) for p in
        (OUTPUT / 'plan.json', OUTPUT / 'simulation-exit.json', OUTPUT / 'result.json',
         Path(plan['work']) / 'commit_trace.csv', Path(plan['work']) / 'vector_trace.csv',
         Path(plan['work']) / 'gap65-observer.tsv') if p.is_file()})
    print(json.dumps(result))
    return int(result['status'] == 'FAIL_OR_MISSING_EVIDENCE')


if __name__ == '__main__':
    raise SystemExit(main())
