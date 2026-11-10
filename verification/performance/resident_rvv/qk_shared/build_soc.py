#!/usr/bin/env python3
"""Committed stage-3 build, accepted dependencies, one directly owned attempt."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
TEMPLATE = OUT/'shared_fma_tagpack_acceptance_20261105_02/soc'
CPU_GATE = OUT/'resident_pv_commit_dirty_20261110_03'
BASE_HELPER = ROOT/'verification/performance/chain_profile/build_soc.py'
CLOSURE_HELPER = ROOT/'verification/performance/resident_rvv/soc_build/build.py'
HELPERS = {
    'base_build.py': (BASE_HELPER, '647d3ac49bbeeeeb5d682b11d0c11a7ded05f84e594f47f3ddf675ef0b283448'),
    'closure_build.py': (CLOSURE_HELPER, 'd40f3dff74a411d75ee189338008b5eb91176d00210563d79cb208e56044afd4'),
}
ANCHORS = {
    TEMPLATE/'report.json': 'e6abfcd7e28efc2e8ae3fd2443027791fdbaca69a56acc8f98b608ab05afd005',
    TEMPLATE/'source-pins.json': '068cd8d15755179e3772fa3559f3a6acffc5a8e7df4086b91798ae426d65357d',
    TEMPLATE/'shared/sources.f': '5ac0bda7b7adf91e25892ba254369c90418879a0cc50f28089fc8dfe79f1800c',
}
TEMPLATE_DUPLICATES = {
    'hardware/deps/cva6/corev_apu/tb/common/mock_uart.sv': 2,
    'hardware/tb/ara_testharness.sv': 2,
}
FILELIST_NORMALIZATION = dict(
    input_sha256=ANCHORS[TEMPLATE/'shared/sources.f'],
    duplicates=TEMPLATE_DUPLICATES, retain='first', removed_occurrences=2)
CPU_ANCHORS = {
    CPU_GATE/'report.json': '2b297b1738ba1aea7e539a83ac6ade6dfd624168590d804fb211dec285b4872d',
    CPU_GATE/'source-pins.json': '97533926e91c80b6a93879895105ada90e6c407de842bda82f3154e0c59dd795',
}
CPU_OVERLAY = dict(target='hardware/deps/cva6/core/commit_stage.sv',
    dependency_revision='b29fd3cf906e7f4c71da4c2f46451c4c60a4487f',
    before_sha256='bf59bfa36960ec6227cb49d86e60f8b8f9507590f64ecfafffa9d8d8f94abb60',
    after_sha256='ce293df18df94a81a0e4fe99ebc798a356c437219de79d79f900bf2362f93249',
    patch_sha256='b4fe150d85074ce51acbddcb88600f359503b60427337919df3350f1acb13c00',
    native_fp_expression_unchanged=True, fflags_logic_unchanged=True)
LOCK_SHA = '4572274dd387f2b7f59038fd9186c4517eee0eeb39464819de4e9afe976329cd'
OWN = ('build_soc.py', 'test_build_soc.py')
CONFIG = dict(schema_version=1, config='stage3_resident_qk_pv', nr_lanes=4, vlen=1024,
    qbs_enabled=1, akv_enabled=1, akv_v2_enabled=1, sim_l2_bytes=16777216,
    shared_simd_multiplier=1, shared_fma=0, qbs_lane_multiplier=0,
    resident_pv_enabled=1, resident_qk_enabled=1, resident_capability=0, ideal_dispatcher=0)
IMAGE_CONTRACT = dict(NrLane=4, VLEN=1024, AXI=128, L2sim_bytes=16777216,
    shared_integer_multiply=True, EnableSharedFma=0, resident_pv=True, resident_qk=True)
MODULES = (
    ('hardware/src/lane/vmfpu.sv', ('hardware/src/lane/qbs_lane_mul_borrow.sv',)),
    ('hardware/src/vlsu/akv/akv_engine.sv', (
        'hardware/src/lane/akv_resident_pv_lane.sv',
        'hardware/src/vlsu/akv/akv_resident_pv_group.sv',
        'hardware/src/vlsu/akv/resident_payload_fanout.sv',
        'hardware/src/vlsu/akv/akv_resident_pv_reader.sv',
        'hardware/src/vlsu/akv/akv_resident_pv_import.sv',
        'hardware/src/vlsu/akv/akv_resident_pv_control.sv')),
)
METAFILES = ('source.tar', 'sources.f', 'elfloader.o', 'cpu-overlay.json', 'plan.json',
             'inventory.json', 'closure.json', 'sim/simulator.conf', 'sim/source_manifest.json')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            value.update(chunk)
    return value.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def verify(pins):
    require(bool(pins), 'Empty inventory')
    for path, expected in pins.items():
        require(Path(path).is_file() and sha(path) == expected, 'Identity drift: '+str(path))


def load(path, name, expected=None):
    if expected is not None:
        verify({path: expected})
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def helpers(inputs=None):
    return tuple(load(inputs/name if inputs else path, 'stage3_'+name[:-3], digest)
                 for name, (path, digest) in HELPERS.items())


def files(root, exclude=(), dpi_link=False):
    """Exact file membership; the one archived DPI link must resolve internally."""
    require(root.is_dir() and not root.is_symlink(), 'Missing/linked inventory root')
    result = {}
    for path in sorted(root.rglob('*')):
        name = path.relative_to(root).as_posix()
        if name in exclude:
            continue
        if path.is_symlink():
            require(dpi_link and name == 'hardware/tb/dpi/elfloader.cc' and
                    path.resolve().is_relative_to(root/'hardware/deps') and path.is_file(),
                    'Unexpected link: '+str(path))
        elif path.is_dir():
            continue
        require(path.is_file(), 'Nonregular input: '+str(path))
        result[str(path)] = sha(path)
    return result


def exact_files(root, expected, **kwargs):
    require(files(root, **kwargs) == expected, 'Exact file inventory drift: '+str(root))
    wanted = {parent for name in expected for parent in Path(name).parents
              if parent != root and parent.is_relative_to(root)}
    actual = {p for p in root.rglob('*') if p.is_dir() and not p.is_symlink()}
    require(actual == wanted, 'Unexpected/stale directory: '+str(root))


def output_path(path, prefix='stage3_soc_'):
    path = Path(path).absolute()
    require(path == path.resolve() and path.parent == OUT and
            re.fullmatch(re.escape(prefix)+r'[A-Za-z0-9_-]{1,100}', path.name),
            'Use a fresh direct signoff output')
    return path


def template_inputs():
    verify(ANCHORS)
    require(read(TEMPLATE/'report.json')['state'] == 'PASS', 'Unaccepted template')
    inherited = read(TEMPLATE/'source-pins.json')
    root = TEMPLATE/'shared/source'
    pins = {p: h for p, h in inherited.items() if Path(p).is_relative_to(root)}
    exact_files(root, pins, exclude=('install',))
    verify({TEMPLATE/'elfloader.o': inherited[str(TEMPLATE/'elfloader.o')]})
    require(sha(root/'Bender.lock') == LOCK_SHA, 'Template dependency lock drift')
    deps = {p: h for p, h in pins.items() if Path(p).is_relative_to(root/'hardware/deps')}
    require(deps and inherited[str(TEMPLATE/'shared/sources.f')] ==
            ANCHORS[TEMPLATE/'shared/sources.f'], 'Unaccepted filelist/dependencies')
    return deps


def check_cpu_gate():
    verify(CPU_ANCHORS)
    report, pins = read(CPU_GATE/'report.json'), read(CPU_GATE/'source-pins.json')
    require(all(report.get(k) == v for k, v in dict(state='PASS', post_pins_match=True,
        post_image_match=True, checks=72, configurations=2, original_failures=23,
        fixed_failures=0, non_dirty_equal=72, original_bug_reproduced=True,
        native_fp_and_fflags_unchanged=True, soc_acceptance=False, overlay=CPU_OVERLAY,
        source_pins_sha256=CPU_ANCHORS[CPU_GATE/'source-pins.json']).items()), 'CPU gate contract drift')
    frozen = {p: h for p, h in pins.items() if Path(p).is_relative_to(CPU_GATE/'inputs')}
    exact_files(CPU_GATE/'inputs', frozen)
    verify(report['artifacts'])
    helper = CPU_GATE/'inputs/test/run.py'
    cpu = load(helper, 'stage3_cpu_overlay', frozen[str(helper)])
    return cpu, report, {str(p): h for p, h in CPU_ANCHORS.items()} | frozen


def insert_modules(text, root):
    lines = text.splitlines()
    for anchor, modules in MODULES:
        marker = str(root/anchor)
        require(lines.count(marker) == 1, 'Missing or duplicate module anchor: '+anchor)
        added = [str(root/p) for p in modules]
        require(not any(p in lines or not Path(p).is_file() for p in added),
                'Duplicate or missing resident module')
        index = lines.index(marker)
        lines[index:index] = added
    require(not any('ARA_AKV_RESIDENT_' in s or 'ARA_QBS_LANE_MUL_ENABLE' in s for s in lines),
            'Template already changes resident or stage-2 selection')
    return '\n'.join(lines+['+define+ARA_AKV_RESIDENT_PV_ENABLE=1',
                           '+define+ARA_AKV_RESIDENT_QK_ENABLE=1'])+'\n'


def normalize_template(text, closure):
    """Remove only the two repeated sources in the exact accepted Nov5 list."""
    require(hashlib.sha256(text.encode()).hexdigest() == FILELIST_NORMALIZATION['input_sha256'],
            'Unaccepted normalization input')
    root = TEMPLATE/'shared/source'
    sources, _, _ = closure.entries(text, root)
    counts = Counter(p.relative_to(root).as_posix() for p in sources)
    require({p: n for p, n in counts.items() if n > 1} == TEMPLATE_DUPLICATES,
            'Accepted template duplicate pattern drift')
    allowed = {str(root/p) for p in TEMPLATE_DUPLICATES}
    seen, kept, removed = set(), [], 0
    for line in text.splitlines(keepends=True):
        token = line.strip()
        if token in allowed:
            if token in seen:
                removed += 1
                continue
            seen.add(token)
        kept.append(line)
    require(removed == FILELIST_NORMALIZATION['removed_occurrences'],
            'Unexpected normalization removal count')
    return ''.join(kept)


def extract_archive(data, source, allowed):
    # A template first-party directory must never survive a commit deletion.
    require(all(Path(p).is_relative_to(source/'hardware/deps') for p in files(source)),
            'Stale first-party source before archive')
    require(all(p == source/'hardware' or p.is_relative_to(source/'hardware/deps')
                for p in source.rglob('*')), 'Stale first-party directory before archive')
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        seen = set()
        for item in archive:
            path = Path(item.name)
            require(not path.is_absolute() and '..' not in path.parts and
                    item.name not in seen and (item.isfile() or item.isdir() or item.issym()),
                    'Unsafe/duplicate archive member')
            seen.add(item.name)
            roots = [Path(p) for p in allowed]
            require(any(path == p or path.is_relative_to(p) or
                        (item.isdir() and p.is_relative_to(path)) for p in roots),
                    'Unselected archive member')
            dest = source/path
            require(not dest.is_symlink() and dest.resolve().is_relative_to(source),
                    'Archive destination escapes source')
            if item.isdir():
                dest.mkdir(parents=True, exist_ok=True)
            elif item.issym():
                target = (dest.parent/item.linkname).resolve()
                require(str(path) == 'hardware/tb/dpi/elfloader.cc' and
                        target.is_relative_to(source/'hardware/deps') and target.is_file(),
                        'Unexpected archive symlink')
                dest.symlink_to(item.linkname)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with dest.open('xb') as stream:
                    stream.write(archive.extractfile(item).read())


def policy(source, text, command, closure):
    sources, _, defines = closure.entries(text, source)
    require(len(sources) == len(set(sources)), 'Duplicate compiler source')
    closure.configuration(defines, command, True)
    require(defines.get('ARA_AKV_RESIDENT_QK_ENABLE') == '1' and
            not {'ARA_QBS_LANE_MUL_ENABLE', 'TARGET_SRAM_MC'} & defines.keys(),
            'Wrong QK/multiplier/memory configuration')
    require(sha(source/'Bender.lock') == LOCK_SHA and
            sha(source/CPU_OVERLAY['target']) == CPU_OVERLAY['after_sha256'],
            'Dependency lock/CPU overlay mismatch')
    ara = (source/'hardware/include/ara_pkg.sv').read_text()
    pkg = (source/'hardware/include/akv_pkg.sv').read_text()
    require('VAKVQK' in ara and "localparam bit EnableSharedFma = 1'b0;" in ara,
            'Missing committed QK or wrong FMA selection')
    for mode in ('pv', 'qk'):
        require(f"localparam bit AkvResident{mode.title()}Supported = 1'b0;" in pkg,
                'Resident capability advertised')
        body = re.search(r'function automatic logic \[63:0\] akv_resident_'+mode+
                         r'_capability_word\(.*?endfunction', pkg, re.S)
        require(body is not None and "return '0;" in body.group(), 'Capability function drift')


def environment():
    env = {k: os.environ[k] for k in ('VCS_HOME', 'VCS_ARCH_OVERRIDE', 'LM_LICENSE_FILE',
        'SNPSLMD_LICENSE_FILE', 'LD_LIBRARY_PATH', 'TMPDIR') if k in os.environ}
    return dict(env, PATH='/usr/bin:/bin', HOME=os.environ.get('HOME', '/home/wangwy'),
                LC_ALL='C', PYTHONDONTWRITEBYTECODE='1')


def compile_command(out, vcs, base):
    return [vcs, '-full64', '-sverilog', '+v2k', '-Mlib=./incremental_db', '-Mupdate',
        '-j8', '-lca', '+nospecify', '+notimingchecks', '+lint=TFIPC-L', '+vpi', '+lint=PCWM',
        '+error+30', '-ntb_opts', 'uvm-1.2', '-top', 'ara_tb', '-timescale=1ns/100fs',
        '+define+SIMULATION', '+define+no_warning', '+define+TSMC_NO_WARNING',
        '+define+ARA_NO_FSDB', '+define+ARA_FAIL_FAST_ASSERTS', '+define+ARA_VERIFY_UVM_CVXIF',
        '+define+ARA_SHARED_SIMD_MUL', '-f', str(out/'sources.f'), str(out/'elfloader.o'),
        *(str(out/'source'/p) for p in base.UVM), '-l', 'comp.vcs.log']


def prepare(out, revision, parent_ready=False):
    out = output_path(out)
    require(parent_ready and re.fullmatch('[0-9a-f]{40}', revision or ''),
            'Explicit production commit and parent component-gate acceptance required')
    require(not out.exists(), 'Preserve old output')
    require(subprocess.check_output(['git', '-C', str(OUT.parent.parent), 'branch', '--show-current'],
            text=True).strip() == 'ara_dsa_signoff_integration', 'Wrong verification branch')
    actual = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', revision+'^{commit}'],
                                     text=True).strip()
    require(actual == revision, 'Not an exact commit')
    base, closure = helpers()
    deps = template_inputs()
    cpu, cpu_report, cpu_pins = check_cpu_gate()
    vcs = Path(shutil.which('vcs') or '/missing-vcs').resolve(strict=True)
    out.mkdir()
    source, inputs, sim = out/'source', out/'inputs', out/'sim'
    for path in (source, inputs, sim):
        path.mkdir()
    original = TEMPLATE/'shared/source'
    for name in deps:
        dest = source/Path(name).relative_to(original)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(name, dest)
        require(sha(dest) == deps[name], 'Dependency copy drift')
    archive = subprocess.check_output(['git', '-C', str(ROOT), 'archive', revision, *base.ARCHIVE_PATHS])
    (out/'source.tar').write_bytes(archive)
    extract_archive(archive, source, base.ARCHIVE_PATHS)
    overlay = cpu.apply_to_snapshot(source)
    require(overlay == CPU_OVERLAY, 'Overlay not bound to PASS03')
    save(out/'cpu-overlay.json', overlay)
    accepted = normalize_template((TEMPLATE/'shared/sources.f').read_text(), closure)
    text = insert_modules(base.freeze_filelist(accepted, original, source), source)
    (out/'sources.f').write_text(text)
    shutil.copyfile(TEMPLATE/'elfloader.o', out/'elfloader.o')
    for name in OWN:
        shutil.copyfile(HERE/name, inputs/name)
    for name, (path, digest) in HELPERS.items():
        shutil.copyfile(path, inputs/name)
        verify({inputs/name: digest})
    save(inputs/'cpu-gate-report.json', cpu_report)
    command = compile_command(out, str(vcs), base)
    policy(source, text, command, closure)
    (sim/'simulator.conf').write_text(''.join(f'{k}={v}\n' for k, v in CONFIG.items()))
    plan = dict(schema='stage3-soc-build-v1', revision=revision, parent_components_accepted=True,
        command=command, configuration=CONFIG, image_contract=IMAGE_CONTRACT, cpu_overlay=overlay,
        filelist_normalization=FILELIST_NORMALIZATION,
        template_anchors={str(p): h for p, h in ANCHORS.items()}, cpu_gate=str(CPU_GATE),
        environment=environment(), python=str(Path(sys.executable).resolve()),
        raw_dirty_sources_used=False, automatic_retry=False)
    save(out/'plan.json', plan)
    extras = [source/p for p in base.UVM]
    save(out/'closure.json', closure.closure(text, source, extras))
    inventory = dict(source=files(source, dpi_link=True), inputs=files(inputs))
    save(out/'inventory.json', inventory)
    pins = inventory['source'] | inventory['inputs'] | {str(out/n): sha(out/n) for n in METAFILES
                                                     if n != 'sim/source_manifest.json'}
    save(sim/'source_manifest.json', closure.source_manifest(text, source, out/'sources.f', extras, pins))
    pins[str(sim/'source_manifest.json')] = sha(sim/'source_manifest.json')
    # Provenance receipts are immutable; never inherit their live RTL/document pins.
    pins.update({str(p): h for p, h in ANCHORS.items()})
    pins.update(cpu_pins)
    for p in (vcs, Path(plan['python']), Path('/usr/bin/systemctl'), Path('/usr/bin/systemd-run')):
        pins[str(p.resolve())] = sha(p)
    verify(pins)
    save(out/'source-pins.json', pins)
    save(out/'prepared.json', dict(state='PREPARED_NOT_COMPILED', source_pins_sha256=sha(out/'source-pins.json')))
    verify_prepared(out)
    return plan


def verify_prepared(out):
    out = output_path(out)
    pins, plan = read(out/'source-pins.json'), read(out/'plan.json')
    require(read(out/'prepared.json') == dict(state='PREPARED_NOT_COMPILED',
            source_pins_sha256=sha(out/'source-pins.json')), 'Prepared receipt drift')
    verify(pins)
    base, closure = helpers(out/'inputs')
    inventory = read(out/'inventory.json')
    exact_files(out/'source', inventory['source'], dpi_link=True)
    exact_files(out/'inputs', inventory['inputs'])
    require(set(inventory['inputs']) == {str(out/'inputs'/p) for p in
            (*OWN, *HELPERS, 'cpu-gate-report.json')}, 'Unexpected frozen helper set')
    mandatory = inventory['source'] | inventory['inputs'] | {str(out/n): sha(out/n) for n in METAFILES}
    require(all(pins.get(p) == h for p, h in mandatory.items()), 'Missing mandatory input pin')
    require(plan['schema'] == 'stage3-soc-build-v1' and plan['cpu_gate'] == str(CPU_GATE) and
            plan['filelist_normalization'] == FILELIST_NORMALIZATION and
            plan['configuration'] == CONFIG and plan['image_contract'] == IMAGE_CONTRACT and
            plan['cpu_overlay'] == read(out/'cpu-overlay.json') == CPU_OVERLAY and
            plan['parent_components_accepted'] is True and re.fullmatch('[0-9a-f]{40}', plan['revision']) and
            plan['raw_dirty_sources_used'] is False and plan['automatic_retry'] is False and
            plan['command'] == compile_command(out, plan['command'][0], base), 'Build selection drift')
    require(pins.get(plan['command'][0]) == sha(plan['command'][0]) and
            pins.get(plan['python']) == sha(plan['python']), 'Unpinned tool')
    require((out/'sim/simulator.conf').read_text() == ''.join(f'{k}={v}\n' for k, v in CONFIG.items()),
            'Simulator configuration drift')
    text, source = (out/'sources.f').read_text(), out/'source'
    accepted = normalize_template((TEMPLATE/'shared/sources.f').read_text(), closure)
    expected = insert_modules(base.freeze_filelist(accepted,
                              TEMPLATE/'shared/source', source), source)
    require(text == expected and plan['template_anchors'] == {str(p): h for p, h in ANCHORS.items()},
            'Filelist is not the accepted template successor')
    verify(ANCHORS)
    verify(CPU_ANCHORS)
    require(read(out/'inputs/cpu-gate-report.json') == read(CPU_GATE/'report.json'),
            'CPU overlay gate receipt drift')
    verify_snapshot(out, plan['revision'], base.ARCHIVE_PATHS, inventory['source'])
    policy(source, text, plan['command'], closure)
    extras = [source/p for p in base.UVM]
    closure.verify_closure(read(out/'closure.json'), text, source, extras)
    require(read(out/'sim/source_manifest.json') ==
            closure.source_manifest(text, source, out/'sources.f', extras, pins), 'Source manifest drift')
    return plan, pins


def verify_snapshot(out, revision, allowed, actual):
    """Reconstruct membership from accepted dependency pins plus the Git archive."""
    original = TEMPLATE/'shared/source'
    inherited = read(TEMPLATE/'source-pins.json')
    expected = {str(out/'source'/Path(p).relative_to(original)): h for p, h in inherited.items()
                if Path(p).is_relative_to(original/'hardware/deps')}
    target = str(out/'source'/CPU_OVERLAY['target'])
    require(expected.get(target) == CPU_OVERLAY['before_sha256'], 'CPU dependency preimage drift')
    expected[target] = CPU_OVERLAY['after_sha256']
    seen = set()
    with tarfile.open(out/'source.tar') as archive:
        require(archive.pax_headers.get('comment') == revision, 'Archive commit mismatch')
        for item in archive:
            path = Path(item.name)
            require(not path.is_absolute() and '..' not in path.parts and item.name not in seen,
                    'Unsafe/duplicate archived path')
            seen.add(item.name)
            require(any(path == Path(p) or path.is_relative_to(p) or
                        (item.isdir() and Path(p).is_relative_to(path)) for p in allowed),
                    'Unselected archived path')
            dest = out/'source'/path
            if item.isfile():
                expected[str(dest)] = hashlib.sha256(archive.extractfile(item).read()).hexdigest()
                require(not dest.is_symlink(), 'Archived regular file replaced with link')
            elif item.issym():
                require(item.name == 'hardware/tb/dpi/elfloader.cc' and dest.is_symlink() and
                        os.readlink(dest) == item.linkname and
                        dest.resolve().is_relative_to(out/'source/hardware/deps'),
                        'Archived DPI link drift')
                expected[str(dest)] = expected[str(dest.resolve())]
            else:
                require(item.isdir(), 'Nonregular archived input')
    require(expected == actual, 'Snapshot differs from committed archive/accepted dependencies')


def image_inventory(sim):
    simv, directory = sim/'simv', sim/'simv.daidir'
    require(simv.is_file() and not simv.is_symlink() and os.access(simv, os.X_OK) and
            simv.stat().st_size > 0, 'Missing executable image')
    members = files(directory)
    require(str(directory/'.daidir_complete') in members and
            any(Path(p).suffix == '.so' and Path(p).stat().st_size > 0 for p in members),
            'Incomplete simulator image')
    return members | {str(simv): sha(simv)}


def direct_owner(cgroup, unit, main_pid, own_pid):
    require(cgroup.endswith('/'+unit) and main_pid == own_pid and own_pid > 1,
            'Worker must be the direct systemd MainPID')


def owner(unit):
    cgroup = Path('/proc/self/cgroup').read_text().strip().splitlines()[-1].split(':', 2)[-1]
    main = int(subprocess.check_output(['/usr/bin/systemctl', '--user', 'show', unit,
               '--property=MainPID', '--value'], text=True, timeout=10).strip())
    direct_owner(cgroup, unit, main, os.getpid())
    return dict(main_pid=main, owner_pid=os.getpid(), cgroup=cgroup, unit=unit)


def claim_attempt(out, review, unit, terminal='build.json'):
    require(review == sha(out/'source-pins.json'), 'Parent review hash mismatch')
    require(not any((out/n).exists() for n in
            ('attempt.json', terminal, 'tests.log', 'compile.log', 'owner.json')),
            'One-shot evidence already exists; use a fresh output')
    ownership = owner(unit)
    save(out/'attempt.json', dict(review_sha256=review, **ownership))
    save(out/'owner.json', ownership)
    return ownership


def service_unit(out):
    return 'stage3-build-'+out.name+'.service'


def service_command(out, review):
    plan, _ = verify_prepared(out)
    require(review == sha(out/'source-pins.json'), 'Parent review hash mismatch')
    require(not (out/'attempt.json').exists() and not (out/'build.json').exists(), 'Already attempted')
    return ['/usr/bin/systemd-run', '--user', '--unit='+service_unit(out),
        '--property=WorkingDirectory='+str(out), '--property=RuntimeMaxSec=7800',
        '--property=KillMode=control-group', '--property=TimeoutStopSec=20',
        '--property=StandardOutput=append:'+str(out/'service.stdout.log'),
        '--property=StandardError=append:'+str(out/'service.stderr.log'),
        plan['python'], '-B', '-u', str(out/'inputs/build_soc.py'), 'execute',
        '--output', str(out), '--review-sha256', review]


def evidence(out):
    names = ('prepared.json', 'source-pins.json', 'attempt.json', 'owner.json', 'tests.log',
             'tests.command.json', 'compile.log', 'compile.command.json', 'sim/comp.vcs.log',
             'image-pins.json')
    return {str(out/n): sha(out/n) for n in names}


def execute(out, review):
    out = output_path(out)
    require(Path(__file__).resolve() == out/'inputs/build_soc.py', 'Execute frozen builder')
    ownership = claim_attempt(out, review, service_unit(out))
    base, _ = helpers(out/'inputs')
    status = dict(state='PREFLIGHT', child_pid=None, **ownership)
    report = dict(state='FAIL', full_soc_executed=False, performance_measured=False,
                  hardware_acceptance=False, automatic_retry=False)
    try:
        plan, pins = verify_prepared(out)
        require({p.name for p in (out/'sim').iterdir()} == {'simulator.conf', 'source_manifest.json'},
                'Stale simulator directory')
        os.environ.clear()
        os.environ.update(plan['environment'])
        base.execute([plan['python'], '-B', str(out/'inputs/test_build_soc.py')], out,
                     out/'tests.log', 120, status, out/'status.json', 'TESTING')
        verify_prepared(out)
        base.execute(plan['command'], out/'sim', out/'compile.log', 7200,
                     status, out/'status.json', 'BUILDING')
        for name in ('compile.log', 'sim/comp.vcs.log'):
            require(not re.search(r'(?m)^(?:Error-|Error:|Fatal:|Fatal-)', (out/name).read_text()),
                    'Compilation errors')
        image = image_inventory(out/'sim')
        verify_prepared(out)
        require(sha(out/'source-pins.json') == review, 'Reviewed inventory drift')
        save(out/'image-pins.json', image)
        report.update(state='STAGE3_SOC_BUILT_NOT_EXECUTED', simv=str(out/'sim/simv'),
            revision=plan['revision'], configuration=CONFIG, image_contract=IMAGE_CONTRACT,
            cpu_overlay=CPU_OVERLAY, post_pins_match=True, post_image_match=True,
            source_pins_sha256=review, image_pins=image, artifacts=evidence(out))
    except BaseException as exc:
        report['error'] = repr(exc)
    save(out/'build.json', report)
    status.update(state=report['state'], child_pid=None, finished=datetime.now(timezone.utc).isoformat())
    base.save(out/'status.json', status)
    print(report['state']+' '+str(out/'build.json'), flush=True)
    return int(report['state'] == 'FAIL')


def checked_build(out):
    plan, pins = verify_prepared(out)
    report = read(out/'build.json')
    expected = dict(state='STAGE3_SOC_BUILT_NOT_EXECUTED', simv=str(out/'sim/simv'),
        revision=plan['revision'], configuration=CONFIG, image_contract=IMAGE_CONTRACT,
        cpu_overlay=CPU_OVERLAY, post_pins_match=True, post_image_match=True,
        full_soc_executed=False, performance_measured=False, hardware_acceptance=False,
        automatic_retry=False, source_pins_sha256=sha(out/'source-pins.json'))
    require(all(report.get(k) == v for k, v in expected.items()), 'Unaccepted stage-3 build receipt')
    image = image_inventory(out/'sim')
    require(report['image_pins'] == read(out/'image-pins.json') == image, 'Exact image membership drift')
    require(report['artifacts'] == evidence(out), 'Build evidence drift')
    attempt, ownership = read(out/'attempt.json'), read(out/'owner.json')
    require(attempt == dict(review_sha256=sha(out/'source-pins.json'), **ownership) and
            ownership['unit'] == service_unit(out), 'Owner/review receipt drift')
    direct_owner(ownership['cgroup'], ownership['unit'], ownership['main_pid'], ownership['owner_pid'])
    return report, pins | image | report['artifacts'] | {str(out/'build.json'): sha(out/'build.json')}


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('prepare', 'preflight', 'service-command', 'execute'):
        p = sub.add_parser(action, allow_abbrev=False)
        p.add_argument('--output', type=Path, required=True)
        if action == 'prepare':
            p.add_argument('--revision', required=True)
            p.add_argument('--parent-ready', action='store_true')
        if action in ('service-command', 'execute'):
            p.add_argument('--review-sha256', required=True)
    a = parser.parse_args()
    out = output_path(a.output)
    if a.action == 'prepare':
        prepare(out, a.revision, a.parent_ready)
        print('PREPARED_NOT_COMPILED '+sha(out/'source-pins.json'))
    elif a.action == 'preflight':
        verify_prepared(out)
        print('PREFLIGHT_PASS_NOT_COMPILED')
    elif a.action == 'service-command':
        print(shlex.join(service_command(out, a.review_sha256)))
    else:
        return execute(out, a.review_sha256)
    return 0


if __name__ == '__main__':
    def interrupted(sig, _frame):
        raise InterruptedError('Signal '+str(sig))
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    sys.exit(main())
