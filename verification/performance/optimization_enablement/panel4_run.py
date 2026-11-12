#!/usr/bin/env python3
"""Two distinct firmware versions on one sealed current image; direct systemd owner."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys

from panel4_prepare import ROOT, HERE, OUT, sha, save, require

IMAGE = OUT/'enablement_soc_build_20261111_02'
PROTOCOL = OUT/'stage3_attention_sdk_vcs_20261110_01'
OLD = OUT/'akv-qk-panel4-abba-build-20261023-02'
OLD_SHA = 'b22725d72f7e7467c733471381e8da6226c332954883ee0ab7cb89f60d85da6c'
OWN = ('panel4_run.py', 'panel4_prepare.py', 'panel4_check.py', 'panel4_check_test.py')


def read(path): return json.loads(Path(path).read_text())


def verify(pins):
    require(bool(pins), 'Empty closure')
    for path, digest in pins.items():
        require(sha(path) == digest, 'Identity drift: '+str(path))


def merge(pins, extra):
    require(all(k not in pins or pins[k] == v for k,v in extra.items()), 'Conflicting pin')
    pins.update(extra)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def unit(out): return out.name.replace('_', '-')+'.service'


def image_inventory(simv):
    directory = simv.with_name('simv.daidir')
    members = [p for p in directory.rglob('*') if p.is_file()]
    require(not simv.is_symlink() and not any(p.is_symlink() for p in directory.rglob('*')), 'Linked image')
    return {str(p): sha(p) for p in [simv, *members]}


def prepare(out, firmware):
    require(not out.exists(), 'Preserve earlier run')
    campaign = load(HERE/'soc_campaign.py', 'panel4_existing_soc')
    s = campaign.builder(); b = s.tools()
    hw, pins = campaign.checked_build(s, IMAGE)
    require(hw['configuration'] == s.CONFIG and hw['post_image_match'], 'Not reviewed all-on image')
    fw = read(firmware/'build.json')
    require(fw['state'] == 'PANEL4_AUTO_BUILT_NOT_EXECUTED' and fw['post_pins_match'] and
        fw['source_pins_sha256'] == sha(firmware/'source-pins.json'), 'AUTO firmware gate')
    merge(pins, read(firmware/'source-pins.json')); merge(pins, fw['artifacts'])
    merge(pins, {str(firmware/'build.json'): sha(firmware/'build.json')})
    old_build = read(OLD/'build.json')
    require(old_build['elf_sha256'] == OLD_SHA and sha(old_build['elf']) == OLD_SHA, 'Old ABBA ELF identity')
    historical = ROOT/'verification/akv/results/qk-panel4-attention-20261024.json'
    history = read(historical)
    require(history['state'] == 'PASS' and history['elf_sha256'] == OLD_SHA and
        history['all_outputs_exact_across_modes'], 'Historical same-ELF provenance')
    out.mkdir(); inputs = out/'inputs'; inputs.mkdir()

    def copy(src, dst):
        dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src, dst)
        merge(pins, {str(src): sha(src), str(dst): sha(dst)})

    for name in OWN: copy(HERE/name, inputs/name)
    for rel in ('verification/akv/run_qk_panel4_abba.py', 'verification/akv/run_refill_overlap_probe.py',
        'verification/akv/test_qk_panel4_abba.py', 'verification/qbs/run_half_scale_soc.py',
        'verification/qbs/run_tile_context_engine.py'):
        copy(ROOT/rel, inputs/Path(rel).name)
    for name in ('soc_campaign.py', 'soc_build.py'):
        merge(pins, {str(HERE/name): sha(HERE/name)})
    protocol_pins = read(PROTOCOL/'source-pins.json')
    require(sha(PROTOCOL/'result.json') == campaign.PROTOCOL_SHA and
        sha(PROTOCOL/'source-pins.json') == campaign.PROTOCOL_PINS and read(PROTOCOL/'result.json')['state'] == 'PASS',
        'Independent protocol predecessor identity')
    protocol_root = PROTOCOL/'inputs/verification/ara_verify'
    for src in sorted(protocol_root.rglob('*.py')):
        require(protocol_pins.get(str(src)) == sha(src), 'Unpinned protocol source')
        copy(src, inputs/'verification/ara_verify'/src.relative_to(protocol_root))
    for src in (PROTOCOL/'source-pins.json', PROTOCOL/'result.json', historical, OLD/'build.json'):
        merge(pins, {str(src): sha(src)})
    old_elf = inputs/'historical_explicit_abba.elf'; copy(Path(old_build['elf']), old_elf)
    auto_elf = inputs/'current_auto.elf'; copy(Path(fw['elf']), auto_elf)
    require(sha(old_elf) != sha(auto_elf), 'Two firmware versions must be distinct')
    environment = read(IMAGE/'plan.json')['environment'].copy()
    environment['LD_LIBRARY_PATH'] = str(Path(environment['VCS_HOME'])/'linux64/lib')+':'+environment.get('LD_LIBRARY_PATH', '')
    environment.update(PYTHONPATH=str(inputs/'verification'), PYTHONDONTWRITEBYTECODE='1', READELF='/usr/bin/readelf')
    plan = dict(schema='enablement-panel4-v1', simv=hw['simv'], image_pins=hw['image_pins'],
        image_build=str(IMAGE), image_build_sha256=sha(IMAGE/'build.json'), environment=environment,
        python=str(Path(sys.executable).resolve()), source_revision=fw['sdk_revision'],
        current_native_source_sha256=fw['native_source_sha256'],
        programs=[dict(name='historical_explicit', elf=str(old_elf), elf_sha256=OLD_SHA,
            selection='explicit0/explicit1/explicit1/explicit0; historical SDK binary'),
            dict(name='current_auto', elf=str(auto_elf), elf_sha256=sha(auto_elf),
            selection='explicit0/unset-auto/unset-auto/explicit0/missing-panel4-cap; current single-C SDK overlay')],
        automatic_retry=False, simulation_seconds=10800, protocol_seconds=1200, whole_model_claim=False,
        performance_scope='RNE KV128 captured D128 GQA6 only; no arbitrary T/FRM benefit claim')
    for tool in (Path(plan['python']), Path('/usr/bin/systemctl'), Path('/usr/bin/systemd-run')):
        merge(pins, {str(tool.resolve()): sha(tool.resolve())})
    save(out/'plan.json', plan); merge(pins, {str(out/'plan.json'): sha(out/'plan.json')})
    verify(pins); save(out/'source-pins.json', pins)
    review = sha(out/'source-pins.json')
    save(out/'prepared.json', dict(state='PREPARED_NOT_EXECUTED', source_pins_sha256=review))
    return dict(state='PREPARED_NOT_EXECUTED', review_sha256=review, programs=plan['programs'])


def preflight(out, review):
    require(review == sha(out/'source-pins.json') and read(out/'prepared.json') ==
        dict(state='PREPARED_NOT_EXECUTED', source_pins_sha256=review), 'Reviewed receipt drift')
    pins, plan = read(out/'source-pins.json'), read(out/'plan.json')
    verify(pins)
    require(plan['automatic_retry'] is False and [p['name'] for p in plan['programs']] ==
        ['historical_explicit', 'current_auto'] and
        image_inventory(Path(plan['simv'])) == plan['image_pins'], 'Image/queue drift')
    return plan, pins


def service_command(out, review):
    plan, _ = preflight(out, review)
    return ['/usr/bin/systemd-run', '--user', '--unit='+unit(out), '--property=Type=exec',
        '--property=RuntimeMaxSec=25000', '--property=MemoryMax=8G', '--property=CPUQuota=100%',
        '--property=KillMode=control-group', '--property=TimeoutStopSec=20',
        '--property=StandardOutput=append:'+str(out/'service.stdout.log'),
        '--property=StandardError=append:'+str(out/'service.stderr.log'), plan['python'], '-B', '-u',
        str(out/'inputs/panel4_run.py'), 'execute', '--output', str(out), '--review-sha256', review]


def execute(out, review):
    require(Path(__file__).resolve() == out/'inputs/panel4_run.py', 'Frozen direct worker required')
    plan, pins = preflight(out, review)
    main_pid = int(subprocess.check_output(['/usr/bin/systemctl', '--user', 'show', unit(out),
        '--property=MainPID', '--value'], text=True, timeout=10))
    cgroup = Path('/proc/self/cgroup').read_text().strip().splitlines()[-1].split(':',2)[-1]
    require(main_pid == os.getpid() and cgroup.endswith('/'+unit(out)), 'Not direct systemd owner')
    owner = dict(main_pid=main_pid, cgroup=cgroup, unit=unit(out))
    save(out/'attempt.json', dict(source_pins_sha256=review, **owner))
    status = dict(state='PREFLIGHT', child_pid=None, **owner)

    def state():
        tmp = out/'status.json.partial'; tmp.write_text(json.dumps(status, indent=2)+'\n'); tmp.replace(out/'status.json')

    def run(label, argv, work, seconds):
        save(work/(label+'.command.json'), dict(argv=list(map(str,argv)), cwd=str(work), timeout=seconds))
        with (work/(label+'.console.log')).open('x') as log:
            child = subprocess.Popen(list(map(str,argv)), cwd=work, env=plan['environment'],
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            status.update(state=label.upper(), child_pid=child.pid); state()
            try:
                rc = child.wait(timeout=seconds)
            except BaseException:
                try:
                    os.killpg(child.pid, signal.SIGTERM); child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL); child.wait()
                except ProcessLookupError: pass
                raise
            finally:
                status['child_pid'] = None; state()
        require(rc == 0, 'Command failed: '+label)

    report = dict(state='FAIL', completed=[], automatic_retry=False, fpga_acceptance=False,
                  whole_model_claim=False, source_pins_sha256=review)
    state()
    try:
        run('checker-tests', [plan['python'], '-B', out/'inputs/panel4_check_test.py'], out, 120)
        import panel4_check
        require(Path(panel4_check.old.__file__).resolve() == out/'inputs/run_qk_panel4_abba.py', 'Unfrozen checker import')
        for program in plan['programs']:
            preflight(out, review)
            work = out/program['name']; work.mkdir()
            log, vector, commit = (work/n for n in ('run.vcs.log', 'vector.csv', 'commit.csv'))
            command = [plan['simv'], '-no_save', '-l', log, '+PRELOAD='+program['elf'],
                '+TESTCASE=enablement_panel4_'+program['name'], '+NO_FSDB', '+NO_INSTR_TRACE', '+AKV_PERF', '+AKV_SUMMARY',
                '+COMMIT_TRACE='+str(commit), '+VECTOR_TRACE='+str(vector),
                '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000']
            run('sim-'+program['name'], command, work, plan['simulation_seconds'])
            io = {str(p): sha(p) for p in (log, vector, commit)}
            check = panel4_check.old.check_log if program['name'] == 'historical_explicit' else panel4_check.check_log
            numeric = check(log.read_text()); save(work/'numerical.json', numeric)
            protocol = [plan['python'], '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
                '--require-axi', '--require-axi-write', '--vector-trace', str(vector), '--log', str(log),
                '--simv', plan['simv'], '--elf', program['elf'], '--output', str(work/'protocol.json')]
            run('protocol-'+program['name'], protocol, work, plan['protocol_seconds'])
            proof = read(work/'protocol.json')
            require(proof['status'] == 'PASS' and proof['issues'] == [] and
                proof['elf_sha256'] == program['elf_sha256'] and proof['simv_sha256'] == sha(plan['simv']) and
                proof['log_sha256'] == io[str(log)] and proof['vector_trace_sha256'] == io[str(vector)], 'Protocol identity/verdict')
            require(all(proof['contract_counts'][k] == 0 for k in
                ('exceptions', 'protocol_errors', 'outstanding')), 'Protocol not drained')
            verify(io); preflight(out, review)
            save(work/'result.json', dict(state='PASS', program=program, numerical=numeric,
                protocol_sha256=sha(work/'protocol.json'), io=io, post_pins_match=True, post_image_match=True))
            report['completed'].append(dict(name=program['name'], state='PASS', elf_sha256=program['elf_sha256'],
                result_sha256=sha(work/'result.json'), cycle_reduction_percent=numeric['cycle_reduction_percent']))
        report.update(state='PANEL4_CURRENT_IMAGE_TWO_VERSION_PASS', post_pins_match=True,
            current_native_source_sha256=plan['current_native_source_sha256'], performance_scope=plan['performance_scope'])
    except BaseException as exc:
        report['error'] = repr(exc)
    save(out/'result.json', report); status.update(state=report['state'], child_pid=None); state()
    print(json.dumps(report), flush=True)
    return int(report['state'] == 'FAIL')


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('prepare', 'service-command', 'execute'):
        p = sub.add_parser(action, allow_abbrev=False); p.add_argument('--output', type=Path, required=True)
        if action == 'prepare': p.add_argument('--firmware', type=Path, required=True)
        else: p.add_argument('--review-sha256', required=True)
    a = parser.parse_args(); out = a.output.absolute()
    require(out == out.resolve() and out.parent == OUT and re.fullmatch(r'enablement_panel4_[A-Za-z0-9_-]+',out.name), 'PANEL4 output namespace')
    if a.action == 'prepare': print(json.dumps(prepare(out, a.firmware.resolve(strict=True))))
    elif a.action == 'service-command': print(json.dumps(service_command(out, a.review_sha256)))
    else: return execute(out, a.review_sha256)
    return 0


if __name__ == '__main__':
    def interrupted(sig, frame): raise InterruptedError('Signal '+str(sig))
    for sig in (signal.SIGTERM, signal.SIGINT): signal.signal(sig, interrupted)
    raise SystemExit(main())
