#!/usr/bin/env python3
"""Prepare/check frozen full-SoC DC inputs; only `run` invokes Design Compiler."""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FLOW = Path('backend/syn/ara_soc/v1-dc')
PROFILES = json.loads((HERE / 'profiles.json').read_text())['profiles']
REFERENCE = Path('/home/wangwy/openproject/dc_ara_main_real')
DEFAULT_DEPS = ROOT / 'hardware/build/rce/private_deps_v1'
DC_HOME = '/home/wangwy/software/synopsys/install/syn/syn/T-2022.03-SP2'
TARGETS = ['rtl', 'synthesis', 'cv64a6_imafdcv_sv39',
           'tech_cells_generic_include_tc_sram', 'tech_cells_generic_include_tc_clk',
           'exclude_first_pass_decoder', 'sram_blackbox', 'sram_mc']
REQUIRED = ['ara_rce_pkg.sv', 'reduction_completion_engine.sv',
            'fp32_exact_reduction_accum.sv', 'fp32_exact_reduction_finalize.sv',
            'valu.sv', 'vmfpu.sv', 'operand_requester.sv', 'ara_sequencer.sv', 'ara_soc.sv']


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def call(cmd, **kwargs):
    return subprocess.run([str(x) for x in cmd], check=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs).stdout


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def entries(text):
    """Preserve dependency source order; reject conflicting/unsupported options."""
    defines, includes, sources = {}, [], []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('//'):
            continue
        if line.startswith('+define+'):
            for item in line[len('+define+'):].split('+'):
                name, sep, value = item.partition('=')
                value = value if sep else None
                if name in defines and defines[name] != value:
                    raise ValueError('Conflicting define: ' + name)
                defines[name] = value
        elif line.startswith('+incdir+'):
            includes.extend(Path(p) for p in line[len('+incdir+'):].split('+'))
        elif line.startswith(('+', '-')):
            raise ValueError('Unsupported filelist option: ' + line)
        else:
            p = Path(line)
            if not p.is_absolute() or p.suffix not in ('.v', '.sv'):
                raise ValueError('Expected absolute HDL source: ' + line)
            sources.append(p)
    return defines, list(dict.fromkeys(includes)), list(dict.fromkeys(sources))


def render(defines, includes, sources):
    return '\n'.join(['+incdir+' + str(p) for p in includes] +
                     ['+define+' + k + ('' if v is None else '=' + v)
                      for k, v in defines.items()] + [str(p) for p in sources]) + '\n'


def validate_defines(defines, profile):
    actual = {k: v for k, v in defines.items() if k.startswith('ARA_RED_')}
    if actual != PROFILES[profile]:
        raise ValueError('Reduction defines do not match sealed profile ' + profile)
    if 'ARA_RED_SHARED_ORDERED_ADD' in defines:
        for dependency in ('ARA_RED_ORDERED_FAST_4LANE', 'ARA_RED_ORDERED_SCALAR_ADD',
                           'ARA_RED_ORDERED_OUTPUT_REG'):
            if defines.get(dependency) != '1':
                raise ValueError('Shared ordered backend requires ' + dependency)
        if defines.get('ARA_RED_SHARED_ORDERED_UNITS') not in ('1', '2'):
            raise ValueError('Shared ordered backend requires one or two physical units')
    if 'ARA_RED_SHARED_FORWARD_CAPTURE' in defines and defines.get('ARA_RED_CHAIN_BYPASS_4LANE') != '1':
        raise ValueError('Shared forwarding capture requires chain bypass')
    for key, val in {'NR_LANES': '4', 'VLEN': '1024', 'ARIANE_ACCELERATOR_PORT': '1'}.items():
        if defines.get(key) != val:
            raise ValueError('Wrong hardware parameter: ' + key)
    for key in ('SYNTHESIS', 'TARGET_SYNTHESIS', 'TARGET_SRAM_MC', 'HPDCACHE_ASSERT_OFF'):
        if key not in defines:
            raise ValueError('Missing synthesis define: ' + key)
    if any(k in defines for k in ('IDEAL_DISPATCHER', 'TARGET_NOTSYNTHESIS',
                                 'TARGET_ARA_TEST', 'TARGET_CVA6_TEST', 'FOR_VERIFY', 'SIMULATION')):
        raise ValueError('Simulation-only configuration in synthesis')
    if any(k.startswith(('ARA_QBS', 'ARA_AKV')) for k in defines):
        raise ValueError('Unrelated DSA feature in reduction synthesis')


def libraries(flow):
    # Evaluate library declarations with plain Tcl, never with dc_shell.
    script = 'source {' + str(flow / 'global_scripts/synopsys_dc.setup.env') + '}\n'
    script += 'foreach k [array names STD_LIBRARY_LIST] {foreach p $STD_LIBRARY_LIST($k) {puts $p}}\n'
    script += 'foreach k [array names IP_LIBRARY_LIST] {foreach p $IP_LIBRARY_LIST($k) {puts $p}}\n'
    result = call(['tclsh'], input=script).splitlines()
    main = (flow / 'global_scripts/synopsys_dc.setup.main').read_text()
    result += re.findall(r'(/[^\s"{}]+\.sldb)', main)
    paths = sorted(set(Path(x) for x in result))
    if len(paths) != 11:
        raise ValueError(f'Expected 4 standard-cell + 6 SRAM + DW libraries, got {len(paths)}')
    for path in paths:
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError('Library missing: ' + str(path))
    return paths


def repair_unboxed_loop(source):
    """Keep NaN boxing semantics with statically unrollable loop bounds for DC."""
    old = """      for (int unsigned bit_idx = fmt_width; bit_idx < CVA6Cfg.FLen; bit_idx++) begin
        is_boxed &= value[bit_idx];
      end"""
    new = """      // Constant loop bounds permit synthesis; only upper boxing bits count.
      for (int unsigned bit_idx = 0; bit_idx < CVA6Cfg.FLen; bit_idx++) begin
        if (bit_idx >= fmt_width) is_boxed &= value[bit_idx];
      end"""
    if new in source:
        return source, "already_static_boxing_loop"
    if source.count(old) != 1:
        raise ValueError("Unrecognized NaN boxing loop; inspect before patching")
    return source.replace(old, new), "static_bounds_nan_boxing_loop"


def original_csr_overlay(source):
    """Supply the same backend-busy field consumed by the common CSR repair."""
    anchor = "      fflags_valid  : |fflags_ex_valid_i,\n"
    if source.count(anchor) != 1 or 'fp_csr_busy' in source:
        raise ValueError('Unexpected original dispatcher CSR interface')
    return source.replace(anchor, anchor +
        "      fp_csr_busy   : !ara_idle_i || ara_req_valid_o || acc_req_i.req_valid ||\n"
        "                      state_q != NORMAL_OPERATION,\n")


def prepare(args, out):
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / 'status.json', {'state': 'PREPARING', 'time': now(), 'dc_started': False})
    # Pinned functional dependencies, including inherited local patches.
    deps = args.deps.resolve()
    call([sys.executable, ROOT / 'hardware/scripts/prepare_rce_dependencies.py',
          '--destination', deps, '--verify-only'])
    workspace = out / 'workspace'
    (workspace / 'hardware').mkdir(parents=True)
    source_revision = None
    if args.profile == 'original_30c6971b':
        source_revision = call(['git', '-C', ROOT, 'rev-parse', '30c6971b^{commit}']).strip()
        names = call(['git', '-C', ROOT, 'ls-tree', '-r', '--name-only', source_revision,
                      'hardware/src', 'hardware/include', 'Bender.yml', 'Bender.lock']).splitlines()
        for name in names:
            target = workspace / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(subprocess.check_output(['git', '-C', str(ROOT), 'show',
                                                       source_revision + ':' + name]))
        dispatcher = workspace / 'hardware/src/ara_dispatcher.sv'
        original = dispatcher.read_text()
        dispatcher.write_text(original_csr_overlay(original))
        typedef = workspace / 'hardware/include/ara/intf_typedef.svh'
        original_type = typedef.read_text()
        anchor = next((line for line in original_type.splitlines(True) if 'logic' in line and 'fflags_valid;' in line), None)
        if anchor is None or 'fp_csr_busy' in original_type:
            raise ValueError('Unexpected original accelerator response typedef')
        typedef.write_text(original_type.replace(anchor, anchor + anchor.replace('fflags_valid', 'fp_csr_busy')))
        write_json(out / 'original_overlay.json', {
            'file': 'hardware/src/ara_dispatcher.sv',
            'original_sha256': hashlib.sha256(original.encode()).hexdigest(),
            'compiled_sha256': sha(dispatcher),
            'interface_file': 'hardware/include/ara/intf_typedef.svh',
            'interface_original_sha256': hashlib.sha256(original_type.encode()).hexdigest(),
            'interface_compiled_sha256': sha(typedef),
            'reason': 'Same FP CSR backend-busy signal as current RTL, required by common dependency CSR interlock; baseline is not byte-identical raw 30c6971b'})
    else:
        for name in ('src', 'include'):
            (workspace / 'hardware' / name).symlink_to(ROOT / 'hardware' / name, target_is_directory=True)
        shutil.copy2(ROOT / 'Bender.yml', workspace / 'Bender.yml')
        shutil.copy2(ROOT / 'Bender.lock', workspace / 'Bender.lock')
    (workspace / 'hardware/deps').symlink_to(deps, target_is_directory=True)
    packages = json.loads((ROOT / 'hardware/reduction_deps/manifest.json').read_text())['packages']
    write_json(workspace / 'Bender.local', {'overrides': {
        p['path']: {'path': str(deps / p['path'])} for p in packages if '/' not in p['path']}})
    blackbox = workspace / 'backend/blackbox'
    blackbox.mkdir(parents=True)
    macro_names = re.findall(r'backend/blackbox/(\S+\.v)', (workspace / 'Bender.yml').read_text())
    if len(macro_names) != 5:
        raise ValueError('Review SRAM macro manifest')
    for name in macro_names:
        shutil.copy2(args.reference / 'backend/blackbox' / name, blackbox / name)
    defs = {'NR_LANES': '4', 'VLEN': '1024', 'ARIANE_ACCELERATOR_PORT': '1',
            'SYNTHESIS': None, 'COMMON_CELLS_ASSERTS_OFF': None, 'HPDCACHE_ASSERT_OFF': None}
    defs.update(PROFILES[args.profile])
    command = [str(args.bender), '--local', '-d', str(workspace), 'script', 'verilator', '--no-default-target']
    for target in TARGETS:
        command += ['-t', target]
    for name, value in defs.items():
        command += ['--define', name + ('' if value is None else '=' + value)]
    raw = call(command)
    flist_dir = out / 'backend/flist'
    flist_dir.mkdir(parents=True)
    flist = flist_dir / 'ara_soc_dc.f'
    defines, includes, sources = entries(raw)
    validate_defines(defines, args.profile)
    required = REQUIRED if source_revision is None else ['valu.sv', 'vmfpu.sv',
                'operand_requester.sv', 'ara_sequencer.sv', 'ara_soc.sv']
    missing = set(required) - {p.name for p in sources}
    if missing:
        raise ValueError('Required RTL missing: ' + str(missing))
    if any('/tb/' in str(p) or p.name == 'tc_sram.sv' for p in sources):
        raise ValueError('Testbench or behavioral SRAM in synthesis list')
    flist.write_text(render(defines, includes, sources))
    # Same reviewed dependency fixes as VCS, only in this private run directory.
    call([sys.executable, ROOT / 'hardware/scripts/prepare_reduction_dependency_overlay.py', flist])
    defines, includes, sources = entries(flist.read_text())
    # Tool-portability rewrite in a private copy; pinned dependencies stay intact.
    matches = [i for i, p in enumerate(sources) if p.name == 'fpu_wrap.sv']
    if len(matches) != 1:
        raise ValueError('Expected one scalar FPU wrapper')
    i = matches[0]
    original = sources[i]
    patched, _ = repair_unboxed_loop(original.read_text())
    target = out / 'backend/flist/reduction_dependency_overlay/fpu_wrap.sv'
    target.with_suffix('.sv.original').write_text(original.read_text())
    target.write_text(patched)
    sources[i] = target
    snapshot = out / 'sources'

    def frozen(path):
        return snapshot / str(path).lstrip('/')

    files = set(sources)
    for inc in includes:
        if not inc.is_dir():
            raise ValueError('Missing include directory: ' + str(inc))
        frozen(inc).mkdir(parents=True, exist_ok=True)
        files.update(p for p in inc.rglob('*') if p.is_file() and p.suffix in ('.svh', '.vh', '.h', '.sv', '.v'))
    records = []
    for source in sorted(files):
        dest = frozen(source)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        records.append({'original': str(source.resolve()), 'snapshot': str(dest.relative_to(out)), 'sha256': sha(dest)})
    flist.write_text(render(defines, [frozen(p) for p in includes], [frozen(p) for p in sources]))
    flow = out / FLOW
    for name in ('global_scripts', 'local_scripts', 'run', 'reports', 'outputs', 'inputs/inc'):
        (flow / name).mkdir(parents=True, exist_ok=True)
    for source in (HERE / 'templates').iterdir():
        target = 'run' if source.name == 'run.cmd' else 'local_scripts' if source.suffix == '.sdc' else 'global_scripts'
        shutil.copy2(source, flow / target / source.name)
    (flow / 'run/.synopsys_dc.setup').write_text('# Setup is sourced explicitly by dc.tcl.\n')
    shared_units = int(defines.get('ARA_RED_SHARED_ORDERED_UNITS', '0')) if 'ARA_RED_SHARED_ORDERED_ADD' in defines else 0
    local_ordered = 4 if 'ARA_RED_ORDERED_FAST_4LANE' in defines and not shared_units else 0
    (flow / 'inputs/run_config.tcl').write_text(
        f'set RCE_PROFILE {args.profile}\nset RCE_CLOCK_PERIOD_NS {args.period}\n'
        f'set GUI_MAX_CPU_NUM {args.cores}\nset RCE_EXPECT_ENGINE {int(args.profile not in ("baseline", "original_30c6971b"))}\n'
        f'set RCE_EXPECT_SHARED_ORDERED {shared_units}\nset RCE_EXPECT_LOCAL_ORDERED {local_ordered}\n'
        'set RCE_ELAB_ONLY [expr {[info exists env(RCE_ELAB_ONLY)] && $env(RCE_ELAB_ONLY) == 1}]\n')
    libs = libraries(flow)
    static = [flist, *[p for p in flow.rglob('*') if p.is_file()]]
    if source_revision:
        static.append(out / 'original_overlay.json')
    static += [HERE / 'profiles.json', Path(__file__), ROOT / 'hardware/scripts/prepare_reduction_dependency_overlay.py']
    # Copy the driver/profile provenance; they are not dependencies at DC runtime.
    prov = out / 'provenance'
    prov.mkdir()
    for p in static[-3:]:
        shutil.copy2(p, prov / p.name)
    static = static[:-3] + list(prov.iterdir())
    records += [{'snapshot': str(p.relative_to(out)), 'sha256': sha(p)} for p in static]
    manifest = {'schema': 1, 'prepared_utc': now(), 'repository': str(ROOT),
                'git_head': call(['git', '-C', ROOT, 'rev-parse', 'HEAD']).strip(),
                'git_diff': call(['git', '-C', ROOT, 'diff', '--stat']),
                'rtl_source_revision': source_revision,
                'dependency_policy': 'current pinned functional dependency snapshot and common portability overlays',
                'profile': args.profile, 'defines': defines, 'source_count': len(sources),
                'scope': 'ara_soc: real CVA6 + Ara + AXI/peripherals + 1MiB L2; 4 lanes/VLEN1024',
                'period_ns': args.period, 'setup_uncertainty_ns': .15 * args.period,
                'cores': args.cores, 'container': args.container, 'dc_home': str(args.dc_home),
                'reference': str(args.reference), 'bender_command': command,
                'frozen_files': records,
                'libraries': [{'path': str(p), 'sha256': sha(p)} for p in libs],
                'dc_started': False, 'validation': 'static only; no HDL elaboration or library load by DC'}
    write_json(out / 'manifest.json', manifest)
    check(out, environment=True)
    write_json(out / 'status.json', {'state': 'PREPARED', 'time': now(), 'dc_started': False})
    print(f'PREPARED (no DC invocation): {out}')


def check(out, environment=False):
    manifest = json.loads((out / 'manifest.json').read_text())
    for record in manifest['frozen_files']:
        p = out / record['snapshot']
        if not p.is_file() or sha(p) != record['sha256']:
            raise ValueError('Frozen input changed: ' + str(p))
    for record in manifest['libraries']:
        if sha(record['path']) != record['sha256']:
            raise ValueError('Library changed: ' + record['path'])
    defs, incs, sources = entries((out / 'backend/flist/ara_soc_dc.f').read_text())
    validate_defines(defs, manifest['profile'])
    if defs != manifest['defines']:
        raise ValueError('Filelist/manifest define mismatch')
    for p in incs + sources:
        p.relative_to(out / 'sources')
        if not p.exists():
            raise ValueError('Missing frozen input: ' + str(p))
    if environment:
        paths = [str(out / FLOW / 'run/run.cmd'), str(out / 'backend/flist/ara_soc_dc.f'),
                 manifest['dc_home'] + '/bin/dc_shell-t', *[r['path'] for r in manifest['libraries']]]
        code = 'import os,sys; p=sys.argv[1:]; assert all(os.access(x,os.R_OK) for x in p),p; assert os.access(p[2],os.X_OK); print("Container paths/tool executable: OK (not launched)")'
        print(call(['docker', 'exec', '-u', f'{os.getuid()}:{os.getgid()}', manifest['container'],
                    'python3', '-c', code, *paths]).strip())
    print(f'Static check PASS: {len(sources)} HDL files; {len(manifest["libraries"])} libraries; profile={manifest["profile"]}')
    return manifest


def report(out):
    m = check(out)
    state = json.loads((out / 'status.json').read_text())
    if state['state'] != 'COMPLETE':
        raise ValueError('No completed synthesis; current state=' + state['state'])
    flow = out / FLOW
    log = (flow / 'run/dc.log').read_text(errors='replace')
    if 'DC_FLOW_COMPLETE' not in log.splitlines() or re.search(r'^(Error:|Fatal:|RCE_DC_FAILURE:)', log, re.M):
        raise ValueError('DC log does not certify completion')
    artifacts = [flow / 'outputs' / ('ara_soc_dc' + ext) for ext in ('.ddc', '.v', '.sdc')]
    artifacts += [flow / 'reports' / name for name in
                  ('area.rpt', 'qor.rpt', 'physical_summary.rpt', 'timing_max.rpt',
                   'reg2reg_max.rpt', 'macro_inventory.rpt', 'power_vectorless.rpt')]
    if any(not p.is_file() or not p.stat().st_size for p in artifacts):
        raise ValueError('Missing synthesis result')
    physical = dict(line.split('=', 1) for line in (flow / 'reports/physical_summary.rpt').read_text().splitlines() if '=' in line)
    summary = {'profile': m['profile'], 'scope': m['scope'], 'physical': physical,
               'limits': 'Mapped synthesis estimates, not routed Fmax or workload power',
               'artifacts': [{'path': str(p.relative_to(out)), 'sha256': sha(p)} for p in artifacts]}
    write_json(out / 'synthesis_summary.json', summary)
    print(json.dumps(summary, indent=2))


def run(out, elaborate_only=False):
    # This is the only function that can execute EDA; prepare/check cannot reach it.
    with (out / '.driver.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        m = check(out, environment=True)
        if (out / FLOW / 'run/dc.log').exists() or (out / 'console.log').exists():
            raise ValueError('Run already attempted; prepare a new --out directory')
        command = ['docker', 'exec', '-u', f'{os.getuid()}:{os.getgid()}',
                   '-e', 'DC_HOME=' + m['dc_home'], '-e', 'RCE_ELAB_ONLY=' + str(int(elaborate_only)),
                   '-w', str(out / FLOW / 'run'), m['container'], 'bash', './run.cmd']
        write_json(out / 'launch.json', {'command': command, 'started_utc': now()})
        write_json(out / 'status.json', {'state': 'RUNNING', 'dc_started': True, 'time': now()})
        with (out / 'console.log').open('w') as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        dc_log = out / FLOW / 'run/dc.log'
        text = dc_log.read_text(errors='replace') if dc_log.exists() else ''
        marker = 'DC_ELAB_COMPLETE' if elaborate_only else 'DC_FLOW_COMPLETE'
        ok = result.returncode == 0 and marker in text.splitlines()
        ok = ok and not re.search(r'^(Error:|Fatal:|RCE_DC_FAILURE:)', text, re.M)
        try:
            check(out)
        except Exception:
            ok = False
        write_json(out / 'status.json', {'state': ('ELABORATED' if elaborate_only else 'COMPLETE') if ok else 'FAILED',
                                        'dc_started': True, 'returncode': result.returncode, 'time': now()})
        if not ok:
            raise RuntimeError('DC run failed; see console.log and run/dc.log')
        if not elaborate_only:
            report(out)
        print('Completed:', out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'check', 'run', 'status', 'report'])
    parser.add_argument('--profile', choices=PROFILES, default='full')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--deps', type=Path, default=DEFAULT_DEPS)
    parser.add_argument('--reference', type=Path, default=REFERENCE)
    parser.add_argument('--bender', type=Path, default=Path('/home/wangwy/ara/hardware/bender'))
    parser.add_argument('--dc-home', type=Path, default=Path(DC_HOME))
    parser.add_argument('--container', default='synopsys_workspace')
    parser.add_argument('--period', type=float, default=1.0)
    parser.add_argument('--cores', type=int, default=8)
    parser.add_argument('--elaborate-only', action='store_true', help='run: DC analysis/link only; still launches EDA')
    args = parser.parse_args()
    if not (0 < args.period < 100 and 1 <= args.cores <= 64):
        parser.error('Invalid period/cores')
    out = (args.out or ROOT / 'hardware/build/synthesis' / args.profile).resolve()
    if re.search(r'[\s{}$\[\]"\\]', str(out)):
        parser.error('Run directory must not contain whitespace or Tcl metacharacters')
    if args.action == 'prepare':
        prepare(args, out)
    elif args.action == 'check':
        check(out, environment=True)
    elif args.action == 'run':
        run(out, args.elaborate_only)
    elif args.action == 'report':
        report(out)
    else:
        print((out / 'status.json').read_text())


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print('ERROR:', error, file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stderr, file=sys.stderr)
        sys.exit(1)
