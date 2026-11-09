#!/usr/bin/env python3
"""Explicit-review, frozen-dependency SoC VCS build only. Never runs simv."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
BASE = OUT/'chain_soc_20261107_01'
ADMITTED = OUT/'chain_soc_admitted_20261107_01'
FROZEN = BASE/'source'
ANCHORS = {
    ADMITTED/'build.json': '901787e2c38bb969230ad8425d668db3125ed79a91873240491545b41435dee8',
    ADMITTED/'source-pins.json': 'd5dfa945f80aa6a143e5f5c75ad7349ac6c805672232175cd6a675fef22778d4',
    BASE/'sources.f': 'fff0b5742c3f24c019d843e6a12d24fb06cdbfb5db9e2b5d6f108d3ad503b067',
    BASE/'plan.json': '61e5c612d93c838fb056ccc61008de5220e63f2cc2a396a61816b4289ea55b7f',
}
OVERLAY = (
    'hardware/include/ara_pkg.sv', 'hardware/include/akv_pkg.sv',
    'hardware/src/ara_dispatcher.sv', 'hardware/src/cva6_accel_first_pass_decoder.sv',
    'hardware/src/ara_sequencer.sv', 'hardware/src/lane/lane_sequencer.sv',
    'hardware/src/lane/operand_requester.sv',
    'hardware/src/lane/vector_fus_stage.sv', 'hardware/src/lane/lane.sv',
    'hardware/src/lane/vmfpu.sv', 'hardware/src/ara.sv',
    'hardware/src/vlsu/vlsu.sv', 'hardware/src/vlsu/akv/akv_engine.sv',
)
NEW_RTL = (
    'hardware/src/lane/akv_resident_pv_lane.sv',
    'hardware/src/vlsu/akv/akv_resident_pv_group.sv',
    'hardware/src/vlsu/akv/resident_payload_fanout.sv',
    'hardware/src/vlsu/akv/akv_resident_pv_reader.sv',
    'hardware/src/vlsu/akv/akv_resident_pv_import.sv',
    'hardware/src/vlsu/akv/akv_resident_pv_control.sv',
)
OWN = ('build.py', 'test_build.py', 'README.md')
METADATA = ('Bender.yml', 'Bender.lock', 'hardware/Makefile', 'config/default.mk', 'config/sram.mk')
PV_DEFINE = '+define+ARA_AKV_RESIDENT_PV_ENABLE=1'
BASE_CONFIG = dict(schema_version=2, config='chain_profile_area_baseline', nr_lanes=4, vlen=1024,
    qbs_enabled=1, akv_enabled=1, akv_v2_enabled=1, sim_l2_bytes=16777216,
    shared_simd_multiplier=1, shared_fma=0, ideal_dispatcher=0,
    memory_note='Simulation-only capacity; no memory latency or interface-width change')
CONFIG = dict(BASE_CONFIG, config='resident_pv_soc_candidate', akv_resident_pv_enabled=1,
              akv_resident_pv_capability=0)
IMAGE_CONTRACT = dict(NrLane=4, VLEN=1024, AXI=128, L2sim_bytes=16777216,
                      shared_integer_multiply=True, EnableSharedFma=0)
TOOL_INCLUDES = {'uvm_macros.svh'}
PITON_HEADERS = {
    ('hardware/deps/cva6/core/include/ariane_pkg.sv', 'l15.tmp.h'),
    ('hardware/deps/cva6/core/include/wt_cache_pkg.sv', 'l15.tmp.h'),
    ('hardware/deps/cva6/core/include/wt_cache_pkg.sv', 'define.tmp.h'),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            value.update(chunk)
    return value.hexdigest()


def verify(pins):
    for name, expected in pins.items():
        require(Path(name).is_file() and sha(name) == expected, 'Input identity drift: '+str(name))


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def status_save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')
    temporary.replace(path)


def entries(text, root):
    """The admitted list has only defines, include directories and absolute sources."""
    sources, directories, defines = [], [], {}
    for raw in text.splitlines():
        token = raw.strip()
        if not token or token.startswith('#'):
            continue
        if token.startswith('+define+'):
            for definition in token[len('+define+'):].split('+'):
                name, _, value = definition.partition('=')
                require(re.fullmatch(r'\w+', name), 'Malformed define: '+token)
                value = value or '1'
                require(name not in defines or defines[name] == value, 'Conflicting define: '+name)
                defines[name] = value
        elif token.startswith('+incdir+'):
            for directory in token[len('+incdir+'):].split('+'):
                path = Path(directory)
                require(path.is_absolute() and path.is_relative_to(root), 'Unsealed include: '+directory)
                require('..' not in path.parts, 'Traversing include path')
                directories.append(path)
        else:
            path = Path(token)
            require(path.is_absolute() and path.is_relative_to(root) and '..' not in path.parts,
                    'Unsupported/unsealed filelist entry: '+token)
            sources.append(path)
    return sources, sorted(set(directories)), defines


def configuration(defines, command, pv):
    needed = dict(NR_LANES='4', VLEN='1024', ARA_QBS_ENABLE='1', ARA_AKV_ENABLE='1',
                  ARA_AKV_V2_ENABLE='1', SIM_L2_SIZE_BYTES='16777216', FOR_VERIFY='1')
    require(all(defines.get(k) == v for k, v in needed.items()), 'Baseline configuration drift')
    require(not any(k in defines for k in ('IDEAL_DISPATCHER', 'PITON_ARIANE', 'ARA_SHARED_FMA', 'SYNTHESIS')),
            'Alternative dispatcher/FMA or synthesis define')
    require(defines.get('ARA_AKV_RESIDENT_PV_ENABLE') == ('1' if pv else None),
            'Unexpected resident PV define')
    require('+define+ARA_SHARED_SIMD_MUL' in command and '-top' in command and
            command[command.index('-top')+1] == 'ara_tb', 'Wrong shared integer multiplier/top')
    for token in command:
        require(not token.startswith(('-cm', '+define+IDEAL_DISPATCHER', '+define+PITON_ARIANE', '+define+ARA_SHARED_FMA',
                                       '+define+SYNTHESIS', '-R', '+PRELOAD=')),
                'Execution/coverage/alternative datapath option: '+token)
    require({'-full64', '-sverilog', '-ntb_opts', 'uvm-1.2', '-timescale=1ns/100fs',
             '+define+ARA_VERIFY_UVM_CVXIF', '+define+ARA_FAIL_FAST_ASSERTS',
             '+define+ARA_NO_FSDB'} <= set(command), 'Missing admitted VCS invariants')


def closure(text, source_root, extras):
    sources, directories, defines = entries(text, source_root)
    files = {*sources, *extras, *(source_root/name for name in METADATA)}
    inventory = {}
    for directory in directories:
        require(directory.is_dir(), 'Missing include directory: '+str(directory))
        require(directory.resolve().is_relative_to(source_root.resolve()), 'Escaping include directory')
        members = sorted(p for p in directory.rglob('*') if p.is_file())
        require(members, 'Empty include directory: '+str(directory))
        inventory[str(directory)] = [str(p) for p in members]
        files.update(members)
    # Follow literal includes, including headers adjacent to a source rather than
    # an explicit +incdir. Only vendor UVM macros are supplied by -ntb_opts.
    pending, visited, tool_headers, inactive = list(files), set(), set(), set()
    while pending:
        path = pending.pop()
        require(path.is_file(), 'Missing compiler input: '+str(path))
        if path.is_relative_to(source_root):
            require(path.resolve().is_relative_to(source_root.resolve()), 'Escaping compiler input')
        if path in visited:
            continue
        visited.add(path)
        if path.suffix not in ('.sv', '.svh', '.vh', '.v', '.h'):
            continue
        content = path.read_text()
        for directive in re.findall(r'(?m)^\s*`include\s+([^\n]+)', content):
            require(re.match(r'"[^"]+"', directive), 'Unresolved macro include: '+str(path))
        for include in re.findall(r'`include\s+"([^"]+)"', content):
            require(not Path(include).is_absolute() and '..' not in Path(include).parts,
                    'Unsafe literal include: '+include)
            found = next((base/include for base in (path.parent, *directories) if (base/include).is_file()), None)
            if found is None and path.is_relative_to(source_root) and (
                    str(path.relative_to(source_root)), include) in PITON_HEADERS:
                block = re.search(r'(?m)^`ifdef PITON_ARIANE\s*\n(.*?)^`endif', content, re.S)
                require('PITON_ARIANE' not in defines and block is not None and
                        '`else' not in block[1] and '`if' not in block[1] and
                        content.count('`include "'+include+'"') == 1 and
                        '`include "'+include+'"' in block[1], 'Inactive OpenPiton include guard changed')
                inactive.add((str(path), include, 'PITON_ARIANE'))
                continue
            if found is None and include in TOOL_INCLUDES:
                tool_headers.add(include)
                continue
            require(found is not None and found.is_relative_to(source_root), 'Unsealed literal include: '+include)
            files.add(found)
            pending.append(found)
    for path in files:
        # The accepted DPI source link is internal; copies below materialize bytes.
        if path.is_symlink():
            require(path.resolve().is_relative_to(source_root), 'Escaping frozen symlink: '+str(path))
    return dict(files={str(p): sha(p) for p in sorted(files)},
                include_directories=inventory, tool_includes=sorted(tool_headers),
                inactive_includes=[dict(source=p, header=h, guard=g) for p, h, g in sorted(inactive)])


def verify_closure(saved, text, source_root, extras):
    require(closure(text, source_root, extras) == saved, 'Compiler closure/include inventory drift')


def source_manifest(text, source_root, filelist, extras, pins):
    # Match the public ara_verify.vcs_source_manifest schema/inventory convention.
    sources, directories, _ = entries(text, source_root)
    paths = {*sources, *extras, filelist, *(source_root/p for p in METADATA)}
    headers = {'.h', '.hpp', '.vh', '.svh'}
    for directory in directories:
        paths.update(p for p in directory.rglob('*') if p.is_file() and p.suffix.lower() in headers)
    paths.update(p for p in (source_root/'hardware/tb/dpi').rglob('*')
                 if p.is_file() and p.suffix.lower() in headers | {'.c', '.cc', '.cpp'})
    require(all(pins.get(str(p)) == sha(p) for p in paths), 'Unpinned standard source-manifest input')
    return dict(schema_version=1, repo_root=str(source_root), filelist=str(filelist),
        extra_sources=list(map(str, extras)),
        files=[dict(path=str(p.resolve()), sha256=pins[str(p)]) for p in sorted(paths)])


def rewrite_filelist(text, old_root, new_root):
    sources, _, _ = entries(text, old_root)
    for relative in OVERLAY:
        require(sources.count(old_root/relative) == 1, 'Overlay missing/duplicated in baseline: '+relative)
    require(all(old_root/p not in sources for p in NEW_RTL), 'New module already present in baseline')
    lines = []
    anchor = old_root/'hardware/src/vlsu/akv/akv_engine.sv'
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith('+incdir+'):
            line = '+incdir+' + '+'.join(str(new_root/Path(p).relative_to(old_root))
                                        for p in line[len('+incdir+'):].split('+'))
        elif line and not line.startswith(('+', '#')):
            if Path(line) == anchor:
                lines.extend(str(new_root/p) for p in NEW_RTL)
            line = str(new_root/Path(line).relative_to(old_root))
        lines.append(line)
    lines.append(PV_DEFINE)
    return '\n'.join(lines)+'\n'


def map_command(command, out):
    mapping = {str(BASE/'sources.f'): str(out/'sources.f'),
               str(BASE/'elfloader.o'): str(out/'inputs/elfloader.o'),
               str(BASE/'boundary_monitor.sv'): str(out/'inputs/boundary_monitor.sv')}
    result = []
    for arg in command:
        if arg in mapping:
            arg = mapping[arg]
        elif arg.startswith(str(FROZEN)+'/'):
            arg = str(out/'source'/Path(arg).relative_to(FROZEN))
        result.append(arg)
    require(result.count(str(out/'sources.f')) == 1 and result[result.index('-f')+1] == str(out/'sources.f'),
            'Missing/ambiguous mapped filelist')
    return result


def baseline():
    verify(ANCHORS)
    receipt = json.loads((ADMITTED/'build.json').read_text())
    book = json.loads((ADMITTED/'source-pins.json').read_text())
    require(receipt['state'] == 'CURRENT_AREA_SOC_COMPILE_AUDITED_NOT_EXECUTED' and
            receipt.get('post_pins_match') is True and receipt['configuration'] == BASE_CONFIG and
            receipt['source_pins_sha256'] == sha(ADMITTED/'source-pins.json') and
            receipt.get('execution') == 'NOT_RUN' and receipt.get('original_worker_relabelled') is False,
            'Wrong admitted compile-only predecessor')
    verify(receipt['image_pins'])
    plan = json.loads((BASE/'plan.json').read_text())
    require(plan['configuration'] == BASE_CONFIG, 'Wrong baseline plan')
    expected_command = BASE/'compile.command.json'
    require(book.get(str(expected_command)) == sha(expected_command), 'Baseline command is not admitted')
    require(json.loads(expected_command.read_text())['argv'] == plan['command'], 'Baseline command/plan disagree')
    text = (BASE/'sources.f').read_text()
    _, _, defines = entries(text, FROZEN)
    configuration(defines, plan['command'], False)
    extras = [Path(p) for p in plan['command'] if p.endswith(('.sv', '.o'))]
    require(len(extras) == 6 and [p.suffix for p in extras].count('.o') == 1,
            'Expected DPI loader, four UVM files and frozen boundary monitor')
    graph = closure(text, FROZEN, extras)
    require(all(book.get(name) == digest for name, digest in graph['files'].items()),
            'Unpinned baseline source/header/extra')
    pins = {**{str(k): v for k, v in ANCHORS.items()}, **graph['files'], **receipt['image_pins'],
            str(expected_command): book[str(expected_command)]}
    tool = Path(plan['command'][0])
    require(book.get(str(tool)) == sha(tool), 'Admitted VCS wrapper changed')
    pins[str(tool)] = book[str(tool)]
    verify(pins)
    return receipt, plan['command'], graph, extras, pins


def copy_pin(source, destination, pins, expected):
    require(source.is_file() and sha(source) == expected, 'Copy source drift: '+str(source))
    destination.parent.mkdir(parents=True, exist_ok=True)
    require(not destination.exists(), 'Refusing to overwrite snapshot: '+str(destination))
    shutil.copyfile(source, destination)
    destination.chmod(0o444)
    pins[str(source)] = expected
    pins[str(destination)] = expected
    verify({str(destination): expected})


def overlay_invariants(source, bender):
    package = (source/'hardware/include/ara_pkg.sv').read_text()
    require("localparam bit EnableSharedFma = 1'b0;" in package and
            not re.search(r"EnableSharedFma\s*=\s*1'b1", package), 'Shared-FMA default changed')
    akv = (source/'hardware/include/akv_pkg.sv').read_text()
    require('`ifdef ARA_AKV_RESIDENT_PV_ENABLE' in akv and
            "AkvResidentPvSupported = 1'b0;" in akv, 'PV admission/capability policy changed')
    capability = re.search(r'function automatic[^;]+?\bakv_resident_pv_capability_word\([^;]+;\s*(.*?)endfunction', akv, re.S)
    require(capability is not None and
            re.sub(r'//[^\n]*', '', capability[1]).strip() == "return '0;", 'PV capability must stay zero')
    for relative in NEW_RTL:
        require(bender.count(relative) == 1, 'New module not uniquely listed for Bender review: '+relative)


def output_path(path):
    out = path.resolve()
    require(out.parent == OUT and re.fullmatch(r'[A-Za-z0-9_-]{1,120}', out.name),
            'Use one fresh direct signoff output child')
    return out


def prepare(out, parent_ready=False):
    require(parent_ready, 'Parent is still editing: explicit --parent-ready required before any snapshot')
    require(Path(__file__).resolve() == ROOT/'verification/performance/resident_rvv/soc_build/build.py',
            'Prepare must use the reviewed live harness')
    out = output_path(out)
    require(not out.exists(), 'Output already exists')
    _, command, graph, extras, pins = baseline()
    # Do not inventory the working tree: only these explicit parent-owned files.
    live = [ROOT/p for p in (*OVERLAY, *NEW_RTL, 'Bender.yml')]
    require(all(p.is_file() and not p.is_symlink() for p in live), 'Missing/linked owned overlay input')
    current = {str(p): sha(p) for p in live}
    out.mkdir()
    source, inputs = out/'source', out/'inputs'
    inputs.mkdir()
    mapping = {}
    for name, digest in graph['files'].items():
        path = Path(name)
        destination = source/path.relative_to(FROZEN) if path.is_relative_to(FROZEN) else inputs/path.name
        if path.is_relative_to(FROZEN) and str(path.relative_to(FROZEN)) in OVERLAY:
            # The baseline digest stays pinned as provenance, but only the
            # authorized live replacement is copied into this compiler closure.
            continue
        copy_pin(path, destination, pins, digest)
        mapping[name] = str(destination)
    overlay = []
    for relative in (*OVERLAY, *NEW_RTL):
        original, destination = ROOT/relative, source/relative
        copy_pin(original, destination, pins, current[str(original)])
        mapping[str(FROZEN/relative)] = str(destination)
        overlay.append(dict(path=relative, source=str(original), sha256=current[str(original)],
                            baseline_sha256=graph['files'].get(str(FROZEN/relative)),
                            kind='replacement' if relative in OVERLAY else 'new'))
    copy_pin(ROOT/'Bender.yml', inputs/'audit/Bender.yml', pins, current[str(ROOT/'Bender.yml')])
    overlay_invariants(source, (inputs/'audit/Bender.yml').read_text())
    for name in OWN:
        copy_pin(HERE/name, inputs/name, pins, sha(HERE/name))
    for name, path in (('admitted-build.json', ADMITTED/'build.json'),
                       ('admitted-source-pins.json', ADMITTED/'source-pins.json'),
                       ('baseline-plan.json', BASE/'plan.json'), ('baseline-sources.f', BASE/'sources.f')):
        copy_pin(path, inputs/name, pins, sha(path))
    text = rewrite_filelist((BASE/'sources.f').read_text(), FROZEN, source)
    (out/'sources.f').write_text(text)
    command = map_command(command, out)
    mapped_extras = [Path(mapping[str(p)]) for p in extras]
    private = closure(text, source, mapped_extras)
    _, _, defines = entries(text, source)
    configuration(defines, command, True)
    # Newly introduced includes may only resolve to already admitted bytes or
    # to the explicitly owned RTL. Never pull an extra header from live deps.
    require(all(pins.get(p) == digest for p, digest in private['files'].items()),
            'New compiler closure has an unpinned input')
    config_text = ''.join(f'{key}={value}\n' for key, value in CONFIG.items())
    (out/'sim').mkdir()
    (out/'sim/simulator.conf').write_text(config_text)
    pins[str(out/'sources.f')] = sha(out/'sources.f')
    vcs_manifest = source_manifest(text, source, out/'sources.f', mapped_extras, pins)
    save(out/'sim/vcs_source_manifest.json', vcs_manifest)
    save(out/'closure.json', private)
    save(out/'command.json', command)
    save(out/'overlay.json', dict(overlay=overlay, bender_audit_only=True,
        live_inputs_excluded=['hardware/tb', 'hardware/deps', 'software', 'apps'],
        baseline_testbench_sha256=graph['files'][str(FROZEN/'hardware/tb/ara_tb.sv')]))
    save(out/'selection.json', dict(schema_version=1, configuration=CONFIG, image_contract=IMAGE_CONTRACT,
        baseline=str(BASE), admitted=str(ADMITTED), parent_review_required=True, timeout_seconds=7200,
        execution='NOT_RUN', snapshot_root=str(source), extras=list(map(str, mapped_extras))))
    for path in (out/'sources.f', out/'closure.json', out/'command.json', out/'overlay.json',
                 out/'selection.json', out/'sim/simulator.conf', out/'sim/vcs_source_manifest.json',
                 Path(sys.executable).resolve()):
        pins[str(path)] = sha(path)
    # Pin the executing compiler backend as well as the admitted shell wrapper.
    vcs1 = Path(command[0]).parent.parent/'linux64/bin/vcs1'
    require(vcs1.is_file(), 'Missing VCS compiler backend')
    pins[str(vcs1)] = sha(vcs1)
    verify(current)
    verify(pins)
    verify_closure(private, text, source, mapped_extras)
    save(out/'source-pins.json', pins)
    save(out/'prepared.json', dict(state='PREPARED_NOT_BUILT', parent_review_required=True,
        source_pins_sha256=sha(out/'source-pins.json'), overlay_files=len(overlay),
        source_files=len(private['files']), execution='NOT_RUN', capability=0))
    print('PREPARED_NOT_BUILT '+str(out), flush=True)
    print('review_sha256='+sha(out/'source-pins.json'), flush=True)


def service_unit(out):
    return 'resident-pv-soc-build-'+out.name+'.service'


def service_command(out):
    digest = sha(out/'source-pins.json')
    prepared = json.loads((out/'prepared.json').read_text())
    require(prepared['state'] == 'PREPARED_NOT_BUILT' and prepared['source_pins_sha256'] == digest,
            'Prepared bundle identity changed before review')
    return ['systemd-run', '--user', '--unit='+service_unit(out),
        '--property=WorkingDirectory='+str(out/'sim'), '--property=RuntimeMaxSec=7500',
        '--property=StandardOutput=append:'+str(out/'service.stdout.log'),
        '--property=StandardError=append:'+str(out/'service.stderr.log'),
        '--setenv=PATH='+os.environ.get('PATH', '/usr/bin:/bin'),
        *['--setenv='+k+'='+os.environ[k] for k in ('VCS_HOME', 'LM_LICENSE_FILE',
          'SNPSLMD_LICENSE_FILE', 'LD_LIBRARY_PATH') if k in os.environ],
        sys.executable, '-B', '-u', str(out/'inputs/build.py'), 'build', '--output', str(out),
        '--parent-reviewed', '--review-sha256', digest]


def direct_owner(cgroup, unit, main_pid, own_pid):
    require(unit in cgroup.split('/'), 'Worker is not in its expected systemd service')
    require(main_pid == own_pid, 'Short launcher, not this worker, owns the service')


def compile_process(command, out, timeout):
    state = dict(state='LAUNCHING_VCS_WRAPPER', owner_pid=os.getpid(), child_pid=None,
                 started=datetime.now(timezone.utc).isoformat(), execution='NOT_RUN')
    status_path = out/'status.json'
    status_save(status_path, state)
    env = {key: os.environ[key] for key in ('HOME', 'PATH', 'VCS_HOME', 'VCS_ARCH_OVERRIDE',
        'SNPSLMD_LICENSE_FILE', 'LM_LICENSE_FILE', 'LD_LIBRARY_PATH', 'TMPDIR') if key in os.environ}
    env.update(LC_ALL='C', PYTHONDONTWRITEBYTECODE='1')
    child = None
    try:
        with (out/'compile.log').open('x') as stream:
            child = subprocess.Popen(command, cwd=out/'sim', env=env,
                stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            state.update(state='VCS_WRAPPER_RUNNING', child_pid=child.pid)
            status_save(status_path, state)
            rc = child.wait(timeout=timeout)
        require(rc == 0, 'VCS exited '+str(rc))
    finally:
        if child is not None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()
        state.update(state='COMPILER_EXITED', child_pid=None)
        status_save(status_path, state)


def artifact_pins(out, pins):
    # stdout/stderr/status may still be live while the direct owner closes out.
    paths = {Path(p) for p in pins if Path(p).is_relative_to(out/'source') or
             Path(p).is_relative_to(out/'inputs')}
    paths.update(out/p for p in ('prepared.json', 'source-pins.json', 'compile.log',
        'tests.log', 'image-pins.json', 'sim/comp.vcs.log', 'sources.f', 'closure.json',
        'command.json', 'overlay.json', 'selection.json', 'sim/simulator.conf',
        'sim/vcs_source_manifest.json'))
    return {str(p): sha(p) for p in sorted(paths) if p.is_file()}


def build(out, parent_reviewed, review_sha256):
    require(parent_reviewed, 'Explicit parent review required')
    require(Path(__file__).resolve() == out/'inputs/build.py', 'Use the frozen runner, not live harness')
    require(review_sha256 == sha(out/'source-pins.json'), 'Review does not identify this frozen bundle')
    prepared = json.loads((out/'prepared.json').read_text())
    require(prepared['state'] == 'PREPARED_NOT_BUILT' and prepared['source_pins_sha256'] == review_sha256,
            'Prepared receipt does not bind this source inventory')
    unit = service_unit(out)
    cgroup = Path('/proc/self/cgroup').read_text().strip().splitlines()[-1].split(':', 2)[-1]
    main_pid = int(subprocess.check_output(['systemctl', '--user', 'show', unit,
                                           '--property=MainPID', '--value'], text=True).strip())
    direct_owner(cgroup, unit, main_pid, os.getpid())
    require(not (out/'build.json').exists() and not (out/'compile.log').exists(), 'Build already attempted; preserve it')
    pins = json.loads((out/'source-pins.json').read_text())
    config = json.loads((out/'selection.json').read_text())
    command = json.loads((out/'command.json').read_text())
    graph = json.loads((out/'closure.json').read_text())
    extras = [Path(p) for p in config['extras']]
    report = dict(state='FAIL', execution='NOT_RUN', performance_measured=False,
                  soc_acceptance=False, fpga_acceptance=False)
    try:
        verify(pins)
        verify_closure(graph, (out/'sources.f').read_text(), out/'source', extras)
        require(config['configuration'] == CONFIG and config['image_contract'] == IMAGE_CONTRACT,
                'Image configuration changed')
        with (out/'tests.log').open('x') as stream:
            subprocess.run([sys.executable, '-B', str(out/'inputs/test_build.py')],
                           cwd=out/'inputs', stdout=stream, stderr=subprocess.STDOUT, timeout=60, check=True)
        compile_process(command, out, config['timeout_seconds'])
        text = (out/'compile.log').read_text(errors='replace')
        require(not re.search(r'\b(?:Error-\[|Error:|Fatal:|Fatal-\[)', text), 'Compiler diagnostic')
        require((out/'sim/simv').is_file() and (out/'sim/simv.daidir').is_dir(), 'Missing complete simulator image')
        verify(pins)
        verify_closure(graph, (out/'sources.f').read_text(), out/'source', extras)
        image = {str(p): sha(p) for p in (out/'sim/simv.daidir').rglob('*') if p.is_file()}
        image[str(out/'sim/simv')] = sha(out/'sim/simv')
        save(out/'image-pins.json', image)
        verify(image)
        report.update(state='RESIDENT_PV_SOC_BUILT_NOT_EXECUTED', simv=str(out/'sim/simv'),
            configuration=CONFIG, image_contract=IMAGE_CONTRACT, post_pins_match=True,
            post_image_match=True, image_pins=image, source_pins_sha256=sha(out/'source-pins.json'),
            baseline=str(ADMITTED), dependencies_from_accepted_snapshot=True,
            experimental_direct_wrapper_only=True, capability_advertised=False)
    except Exception as exc:
        report['error'] = str(exc)
    report['artifacts'] = artifact_pins(out, pins)
    save(out/'build.json', report)
    status_save(out/'status.json', dict(state=report['state'], owner_pid=os.getpid(),
        child_pid=None, finished=datetime.now(timezone.utc).isoformat(), execution='NOT_RUN'))
    print(report['state']+' '+str(out/'build.json'), flush=True)
    return int(report['state'] != 'RESIDENT_PV_SOC_BUILT_NOT_EXECUTED')


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest='action', required=True)
    prep = sub.add_parser('prepare', allow_abbrev=False)
    prep.add_argument('--output', type=Path, required=True)
    prep.add_argument('--parent-ready', action='store_true')
    compile_parser = sub.add_parser('build', allow_abbrev=False)
    compile_parser.add_argument('--output', type=Path, required=True)
    compile_parser.add_argument('--parent-reviewed', action='store_true')
    compile_parser.add_argument('--review-sha256', required=True)
    service = sub.add_parser('service-command', allow_abbrev=False)
    service.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = output_path(args.output)
    if args.action == 'prepare':
        prepare(out, args.parent_ready)
        return 0
    if args.action == 'service-command':
        require(json.loads((out/'prepared.json').read_text())['state'] == 'PREPARED_NOT_BUILT',
                'No prepared bundle to review')
        print(shlex.join(service_command(out)))
        return 0
    return build(out, args.parent_reviewed, args.review_sha256)


if __name__ == '__main__':
    def interrupted(sig, _frame):
        raise InterruptedError('Signal '+str(sig))
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    raise SystemExit(main())
