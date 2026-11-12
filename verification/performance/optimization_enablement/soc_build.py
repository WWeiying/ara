#!/usr/bin/env python3
"""One all-on VCS image from sealed Stage3 dependencies; never launches simv."""
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

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
BASE = OUT/'stage3_soc_20261110_02'
BASE_SHA = 'a947cd4ed4dd16c07bfe0335f28c3c13d88178593d4b1b49090bff8d30fd849b'
HELPER_SHA = 'ad6cfb879e5ee61344a92591f2d78dd290e4a649b543e09b7f179ce88c3337b2'
OVERLAYS = {
    'hardware/Makefile': '63cce8ac554f7c517a5ad5a8249f16dc5a8164fbaf6cbe028152994c52568c46',
    'hardware/include/ara_pkg.sv': 'e6e333d6461d8e071543318002798d0c46345b3724f5baad64270ea3e43e9dd5',
    'config/optimizations.mk': '9e8c9daa633f145626b2482d0b0ebff8f696842b18ca9258fa9055808146542f',
}
MONITORS = {
    'loan.sv': ('verification/performance/next_mechanism/stage2/soc_loan_monitor.sv',
                '67f746c59e7ca6f42d4b1b0a76b9d252656159be992f43df37077040353d248b'),
    'fma.sv': ('verification/timing/shared_fma_soc_monitor.sv',
               '0f15fcbbcc5a1fed00dbc292a15b6d48f85971de0c86549b72f24c6240f98cc4'),
}
OWN = ('soc_build.py', 'soc_build_test.py')
CONFIG = dict(schema_version=1, config='candidate_all', nr_lanes=4, vlen=1024,
    qbs_enabled=1, akv_enabled=1, akv_v2_enabled=1, sim_l2_bytes=16777216,
    shared_simd_multiplier=1, shared_fma=1, qbs_lane_multiplier=1,
    resident_pv_enabled=1, resident_qk_enabled=1, resident_capability=0, ideal_dispatcher=0)


def tools():
    path = HERE/'build_soc.py' if (HERE/'build_soc.py').exists() else BASE/'inputs/build_soc.py'
    import hashlib
    require(hashlib.sha256(path.read_bytes()).hexdigest() == HELPER_SHA, 'Sealed Stage3 helper drift')
    spec = importlib.util.spec_from_file_location('enablement_stage3_build', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def require(ok, message):
    if not ok:
        raise ValueError(message)


def output(path):
    path = Path(path).absolute()
    require(path == path.resolve() and path.parent == OUT and
            re.fullmatch(r'enablement_soc_[A-Za-z0-9_-]+', path.name), 'Fresh direct enablement_soc_* required')
    return path


def selected_config(shared):
    require(type(shared) is int and shared in (0, 1), 'FMA selection must be 0 or 1')
    return dict(CONFIG, shared_fma=shared)


def configuration(source, text, command, b, closure, shared=1):
    _, _, defines = closure.entries(text, source)
    required = dict(NR_LANES='4', VLEN='1024', SIM_L2_SIZE_BYTES='16777216', FOR_VERIFY='1',
        ARA_QBS_ENABLE='1', ARA_AKV_ENABLE='1', ARA_AKV_V2_ENABLE='1',
        ARA_AKV_RESIDENT_PV_ENABLE='1', ARA_AKV_RESIDENT_QK_ENABLE='1',
        ARA_QBS_LANE_MUL_ENABLE='1')
    selected_config(shared)
    require(defines.get('ARA_SHARED_FMA') == ('1' if shared else None), 'FMA macro selection drift')
    require(all(defines.get(k) == v for k, v in required.items()), 'All-on filelist selection drift')
    require(not {'SYNTHESIS', 'IDEAL_DISPATCHER', 'PITON_ARIANE', 'TARGET_SRAM_MC'} & defines.keys(),
            'Unexpected synthesis/dispatcher/memory selection')
    require('+define+ARA_SHARED_SIMD_MUL' in command and '-R' not in command and
            not any(s.startswith('-cm') or s.startswith('+PRELOAD=') for s in command),
            'Wrong MUL or build/run/coverage command')
    package = (source/'hardware/include/ara_pkg.sv').read_text()
    require(re.search(r"`ifdef ARA_SHARED_FMA\s+localparam bit EnableSharedFma = 1'b1;\s+"
                      r"`else\s+localparam bit EnableSharedFma = 1'b0;\s+`endif", package),
            'Shared FMA must use the sealed default-OFF macro, not text replacement')
    require(b.sha(source/'Bender.lock') == b.LOCK_SHA and
            b.sha(source/b.CPU_OVERLAY['target']) == b.CPU_OVERLAY['after_sha256'],
            'Locked dependencies / repaired CPU commit-stage identity drift')
    pkg = (source/'hardware/include/akv_pkg.sv').read_text()
    for name in ('Pv', 'Qk'):
        require("localparam bit AkvResident" + name + "Supported = 1'b0;" in pkg,
                'Resident production capability changed')
        body = re.search(r'function automatic logic \[63:0\] akv_resident_' + name.lower() +
                         r'_capability_word\(.*?endfunction', pkg, re.S)
        require(body is not None and "return '0;" in body[0], 'Resident capability function changed')


def prepare(out, revision, ready, shared=1):
    require(ready, 'Configuration owner must confirm sealed READY before snapshot')
    require(re.fullmatch('[0-9a-f]{40}', revision), 'Exact committed main RTL revision required')
    config = selected_config(shared)
    b = tools(); base, closure = b.helpers(BASE/'inputs')
    b.verify({BASE/'build.json': BASE_SHA})
    baseline, inherited = b.checked_build(BASE)
    require(not out.exists(), 'Preserve prior attempt')
    live = {str(ROOT/p): h for p, h in OVERLAYS.items()}
    b.verify(live)
    out.mkdir(); source, inputs, sim = (out/n for n in ('source', 'inputs', 'sim'))
    inputs.mkdir(); sim.mkdir()
    # Exact historical deps already include the CPU retirement fix. No live deps.
    original = BASE/'source'
    deps = {p: h for p, h in b.read(BASE/'inventory.json')['source'].items()
            if Path(p).is_relative_to(original/'hardware/deps')}
    require(deps, 'Missing locked dependency inventory')
    for name, digest in deps.items():
        dest = source/Path(name).relative_to(original)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(name, dest)
        b.verify({dest: digest})
    data = subprocess.check_output(['git', '-C', str(ROOT), 'archive', revision, *base.ARCHIVE_PATHS])
    (out/'source.tar').write_bytes(data)
    b.extract_archive(data, source, base.ARCHIVE_PATHS)
    overlay = []
    for rel, digest in OVERLAYS.items():
        dest = source/rel; before = b.sha(dest) if dest.exists() else None
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/rel, dest); b.verify({dest: digest})
        overlay.append(dict(path=rel, before_sha256=before, after_sha256=digest))
    for name in OWN:
        shutil.copyfile(HERE/name, inputs/name)
    for name in ('build_soc.py', *b.HELPERS):
        shutil.copyfile(BASE/'inputs'/name, inputs/name)
    monitor_pins = {}
    for name, (rel, digest) in MONITORS.items():
        b.verify({ROOT/rel: digest}); shutil.copyfile(ROOT/rel, inputs/name)
        monitor_pins[str(ROOT/rel)] = digest
    shutil.copyfile(BASE/'elfloader.o', out/'elfloader.o')
    text = (BASE/'sources.f').read_text().replace(str(original), str(source))
    require('ARA_SHARED_FMA' not in text and 'ARA_QBS_LANE_MUL_ENABLE' not in text,
            'Predecessor selection changed')
    text += ('+define+ARA_SHARED_FMA=1\n' if shared else '') + '+define+ARA_QBS_LANE_MUL_ENABLE=1\n'
    (out/'sources.f').write_text(text)
    command = []
    for token in b.read(BASE/'plan.json')['command']:
        token = token.replace(str(BASE/'sources.f'), str(out/'sources.f'))
        token = token.replace(str(BASE/'elfloader.o'), str(out/'elfloader.o'))
        token = token.replace(str(original)+'/', str(source)+'/')
        command.append('-j4' if token == '-j8' else token)
    command.extend(str(inputs/n) for n in MONITORS)
    configuration(source, text, command, b, closure, shared)
    extras = [source/p for p in base.UVM] + [inputs/n for n in MONITORS]
    graph = closure.closure(text, source, extras)
    b.save(out/'closure.json', graph)
    (sim/'simulator.conf').write_text(''.join(f'{k}={v}\n' for k, v in config.items()))
    inventory = dict(source=b.files(source, dpi_link=True), inputs=b.files(inputs))
    b.save(out/'inventory.json', inventory)
    pins = inventory['source'] | inventory['inputs'] | live | monitor_pins
    # Keep the predecessor evidence immutable, not its unrelated live documentation.
    pins.update({str(BASE/n): b.sha(BASE/n) for n in ('build.json', 'source-pins.json', 'inventory.json')})
    pins.update({str(original/Path(p).relative_to(source)): h for p, h in inventory['source'].items()
                 if Path(p).is_relative_to(source/'hardware/deps')})
    plan = dict(schema='enablement-soc-build-v1', revision=revision, configuration=config,
        cpu_overlay=baseline['cpu_overlay'], overlays=overlay, command=command,
        dependency_source=str(BASE), live_dependencies_used=False, dirty_tb_used=False,
        environment=b.read(BASE/'plan.json')['environment'], python=str(Path(sys.executable).resolve()),
        compile_seconds=7200, service_seconds=7800, automatic_retry=False)
    b.save(out/'plan.json', plan)
    pins[str(out/'sources.f')] = b.sha(out/'sources.f')
    b.save(sim/'source_manifest.json', closure.source_manifest(text, source, out/'sources.f', extras, pins))
    vcs = Path(command[0]); vcs1 = vcs.parent.parent/'linux64/bin/vcs1'
    for p in (vcs, vcs1, Path(plan['python']), Path('/usr/bin/systemctl'), Path('/usr/bin/systemd-run')):
        pins[str(p.resolve())] = b.sha(p.resolve())
    for n in ('source.tar', 'sources.f', 'elfloader.o', 'plan.json', 'inventory.json', 'closure.json',
              'sim/simulator.conf', 'sim/source_manifest.json'):
        pins[str(out/n)] = b.sha(out/n)
    b.verify(pins); b.save(out/'source-pins.json', pins)
    b.save(out/'prepared.json', dict(state='PREPARED_NOT_COMPILED',
        source_pins_sha256=b.sha(out/'source-pins.json')))
    preflight(out)
    return dict(state='PREPARED_NOT_COMPILED', review_sha256=b.sha(out/'source-pins.json'), cpu_overlay=b.CPU_OVERLAY)


def preflight(out):
    b = tools(); _, closure = b.helpers(out/'inputs')
    pins, plan = b.read(out/'source-pins.json'), b.read(out/'plan.json')
    require(b.read(out/'prepared.json') == dict(state='PREPARED_NOT_COMPILED',
            source_pins_sha256=b.sha(out/'source-pins.json')), 'Prepared review drift')
    b.verify(pins)
    inventory = b.read(out/'inventory.json')
    b.exact_files(out/'source', inventory['source'], dpi_link=True)
    b.exact_files(out/'inputs', inventory['inputs'])
    mandatory = inventory['source'] | inventory['inputs']
    require(all(pins.get(p) == h for p, h in mandatory.items()), 'Missing frozen source/helper pin')
    require(plan['configuration'] == selected_config(plan['configuration']['shared_fma']) and plan['cpu_overlay'] == b.CPU_OVERLAY and
            plan['live_dependencies_used'] is False and plan['dirty_tb_used'] is False,
            'Wrong all-on configuration/CPU provenance')
    text = (out/'sources.f').read_text()
    configuration(out/'source', text, plan['command'], b, closure, plan['configuration']['shared_fma'])
    base, _ = b.helpers(out/'inputs')
    extras = [out/'source'/p for p in base.UVM] + [out/'inputs'/n for n in MONITORS]
    closure.verify_closure(b.read(out/'closure.json'), text, out/'source', extras)
    return plan, pins


def unit(out):
    return 'enablement-soc-build-'+out.name+'.service'


def service(out, review):
    b = tools(); plan, _ = preflight(out)
    require(review == b.sha(out/'source-pins.json') and not (out/'attempt.json').exists(), 'Review / one-shot mismatch')
    return ['/usr/bin/systemd-run', '--user', '--unit='+unit(out), '--property=Type=exec',
        '--property=RuntimeMaxSec=7800', '--property=MemoryMax=16G', '--property=CPUQuota=400%',
        '--property=KillMode=control-group', '--property=TimeoutStopSec=20',
        '--property=StandardOutput=append:'+str(out/'service.stdout.log'),
        '--property=StandardError=append:'+str(out/'service.stderr.log'),
        plan['python'], '-B', '-u', str(out/'inputs/soc_build.py'), 'execute',
        '--output', str(out), '--review-sha256', review]


def execute(out, review):
    require(Path(__file__).resolve() == out/'inputs/soc_build.py', 'Frozen worker required')
    b = tools(); owner = b.claim_attempt(out, review, unit(out))
    base, _ = b.helpers(out/'inputs')
    status = dict(state='PREFLIGHT', child_pid=None, **owner)
    report = dict(state='FAIL', full_soc_executed=False, performance_measured=False, automatic_retry=False)
    try:
        plan, pins = preflight(out)
        require({p.name for p in (out/'sim').iterdir()} == {'simulator.conf', 'source_manifest.json'}, 'Stale build directory')
        os.environ.clear(); os.environ.update(plan['environment'])
        base.execute([plan['python'], '-B', str(out/'inputs/soc_build_test.py')], out/'inputs',
                     out/'tests.log', 120, status, out/'status.json', 'HOST_TESTS')
        base.execute(plan['command'], out/'sim', out/'compile.log', plan['compile_seconds'],
                     status, out/'status.json', 'VCS_COMPILING')
        for name in ('compile.log', 'sim/comp.vcs.log'):
            require(not re.search(r'(?m)^\s*(?:Error-|Error:|Fatal:|Fatal-)', (out/name).read_text()), 'VCS compilation diagnostic')
        image = b.image_inventory(out/'sim'); preflight(out)
        b.save(out/'image-pins.json', image)
        report.update(state='ENABLEMENT_SOC_BUILT_NOT_EXECUTED', configuration=plan['configuration'],
            simv=str(out/'sim/simv'), image_pins=image, cpu_overlay=b.CPU_OVERLAY,
            source_pins_sha256=review, post_pins_match=True, post_image_match=True)
    except BaseException as exc:
        report['error'] = repr(exc)
    b.save(out/'build.json', report)
    print(json.dumps(report), flush=True)
    return int(report['state'] != 'ENABLEMENT_SOC_BUILT_NOT_EXECUTED')


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    sub = parser.add_subparsers(dest='action', required=True)
    for name in ('prepare', 'preflight', 'service-command', 'execute'):
        p = sub.add_parser(name, allow_abbrev=False); p.add_argument('--output', type=Path, required=True)
        if name == 'prepare':
            p.add_argument('--revision', required=True); p.add_argument('--parent-ready', action='store_true')
            p.add_argument('--shared-fma', type=int, choices=(0, 1), default=1)
        if name in ('service-command', 'execute'):
            p.add_argument('--review-sha256', required=True)
    a = parser.parse_args(); out = output(a.output)
    if a.action == 'prepare': print(json.dumps(prepare(out, a.revision, a.parent_ready, a.shared_fma)), flush=True)
    elif a.action == 'preflight': preflight(out); print('PREFLIGHT_PASS')
    elif a.action == 'service-command': print(json.dumps(service(out, a.review_sha256)))
    else: return execute(out, a.review_sha256)
    return 0


if __name__ == '__main__':
    def interrupted(sig, frame):
        raise InterruptedError('Signal '+str(sig))
    for sig in (signal.SIGTERM, signal.SIGINT): signal.signal(sig, interrupted)
    raise SystemExit(main())
