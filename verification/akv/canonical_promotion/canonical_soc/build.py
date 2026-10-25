#!/usr/bin/env python3
"""Actual promoted canonical make compile only; never execute the generated simv."""
import argparse
from collections import Counter
import hashlib
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
ROOT = HERE.parents[3]
PLAN = HERE.parent / 'coherent_package/prepared-01/plan.json'
PLAN_SHA = 'cfda0a82d1c909fb2a0ab3b90278ff339060c96ed4ac81e2f6c69118a3257cba'
OLD_LIST = ROOT / 'verification/out/qbacc-soc-20261023-02/build/hardware-build/vcs/bender_script_default'
OLD_LIST_SHA = '955bd225d99af519234e3ddc76b5fca191dedcf781d32d32b0d6c1cccb3aa4ce'
LOCKED = {
    'Bender.lock': '4572274dd387f2b7f59038fd9186c4517eee0eeb39464819de4e9afe976329cd',
    'config/default.mk': 'f32f797d6bde262af0f9433863ece2bdcbbc4f2c79f05da501a3199cd58bec20',
    'config/sram.mk': 'ebaa57d613374e00aafe54f35afccf6381d2f02539f2328209f6e7069c3edcbe',
    'hardware/bender': '02dbb01d7e44907a1020a55942a917c7420c520e2cb112d88c7c66976cd64f6d',
}
UVM = tuple(ROOT / 'verification/uvm' / name for name in (
    'ara_cvxif_if.sv', 'ara_cvxif_uvm_pkg.sv', 'ara_acc_contract_monitor.sv', 'ara_cvxif_dut_bind.sv'))
INSERTIONS = {
    'hardware/src/vlsu/qbs/qbs_read_engine.sv': ('hardware/src/vlsu/qbs_akv_shared_reader.sv',),
    'hardware/src/vlsu/akv/akv_v2_context.sv': tuple('hardware/src/vlsu/akv/' + n + '.sv' for n in
        ('akv_legacy_repacker', 'akv_q_store', 'akv_unified_context')),
}
FLAGS = dict(config='default', mc='0', qbs='1', akv='0', akv_v2='1', qbs_vrf_continuation='1',
             sim_l2_mb='16', nr_lanes='4', vlen='1024', no_fsdb='1', verify_source_manifest='1',
             verify_uvm_cvxif='1', fail_on_assert='1', verify_axi_delay='0', code_coverage='0',
             ideal_dispatcher='0', store_b_ab_baseline='0', qbs_perf='0')
VCS_FLAGS = ('-full64 -sverilog +v2k -Mlib=./incremental_db -Mupdate -j64 -lca -kdb '
             '-debug_access+all +nospecify +notimingchecks +lint=TFIPC-L +vpi +lint=PCWM '
             '+error+30 -ntb_opts uvm-1.2 -top ara_tb -timescale=1ns/100fs '
             '+define+SIMULATION +define+no_warning +define+TSMC_NO_WARNING '
             '+define+ARA_VERIFY_UVM_CVXIF +define+ARA_FAIL_FAST_ASSERTS +define+ARA_NO_FSDB').split()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def verify(pins):
    for path, sha in pins.items():
        require(digest(path) == sha, 'Input drift: ' + str(path))


def read(path):
    return json.loads(Path(path).read_text())


def guard(root=ROOT, plan=PLAN):
    require(root.resolve() == ROOT and not root.is_symlink(), 'Only the actual canonical source root is allowed')
    require(digest(plan) == PLAN_SHA, 'Coherent plan identity differs')
    report = read(plan)
    require(len(report['files']) == report['target_count'] == 19 and
            len({r['target'] for r in report['files']}) == 19, 'Need the complete nineteen-target promotion')
    for row in report['files']:
        path = root / row['target']
        require(path.is_file() and path.resolve() == path and digest(path) == row['after_sha256'],
                'Canonical promotion incomplete: ' + row['target'])
    for name, sha in LOCKED.items():
        require((root / name).is_file() and digest(root / name) == sha, 'Locked input differs: ' + name)
    require(os.access(root / 'hardware/bender', os.X_OK), 'Bender missing/not executable; no download allowed')
    return report


def tokens(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


def expected_graph(text, root=ROOT):
    lines = tokens(text)
    for anchor, additions in INSERTIONS.items():
        anchor = str(root / anchor)
        require(lines.count(anchor) == 1, 'Changed original source anchor')
        index = lines.index(anchor) + 1
        require(not any(str(root / p) in lines for p in additions), 'Original list already contains new sources')
        lines[index:index] = [str(root / p) for p in additions]
    return lines


def check_graph(actual, expected, repeats, root=ROOT):
    require(tokens(actual) == expected, 'Actual canonical Bender graph/order/defines differs')
    sources = [Path(line) for line in expected if not line.startswith('+')]
    require(all(p.is_absolute() and p.is_relative_to(root / 'hardware') and p.resolve() == p
                for p in sources), 'Noncanonical/snapshot/aliased source in graph')
    counts = Counter(sources)
    observed = {p.relative_to(root).as_posix(): n for p, n in counts.items() if n > 1}
    require(observed == {name: 2 for name in repeats}, 'Unexpected duplicate source')
    for name, sha in repeats.items():
        require(digest(root / name) == sha, 'Inherited duplicate source changed')
    for kind in ('qbs', 'akv'):
        source = root / f'hardware/src/vlsu/{kind}/{kind}_engine.sv'
        text = source.read_text()
        require(counts[source] == 1 and 'reader_req_o' in text and 'reader_rsp_i' in text and
                not re.search(r'\bqbs_read_engine\s*#', text), 'Private/duplicate/nonexternal engine')
    for name in ('hardware/src/vlsu/qbs/qbs_read_engine.sv',
                 'hardware/src/vlsu/qbs_akv_shared_reader.sv',
                 'hardware/src/vlsu/akv/akv_unified_context.sv'):
        require(counts[root / name] == 1, 'Shared module missing/duplicated')


def make_command(output, tools, root=ROOT):
    output = output.resolve()
    require(not output.exists() and not any(output.is_relative_to(root / n) for n in
                ('hardware', 'software', 'verification/akv/canonical_promotion')) and
            not root.is_relative_to(output), 'Use a fresh independent build output')
    # -o suppresses the inherited curl/bootstrap recipe even if Bender disappears.
    return [str(tools['make']), '--no-print-directory', '-C', str(root / 'hardware'),
            '-o', str(root / 'hardware/bender'), 'compile', *[k + '=' + v for k, v in FLAGS.items()],
            'BENDER=' + str(root / 'hardware/bender'), 'CXX=' + str(tools['g++']),
            'buildpath=' + str(output / 'hardware-build'), 'sim_dir=' + str(output / 'sim'),
            'verify_extra_sources=' + ' '.join(map(str, UVM))]


def expected_vcs(output, vcs):
    return [str(vcs), *VCS_FLAGS, '-f', str(output / 'hardware-build/vcs/bender_script_default'),
            str(output / 'hardware-build/work-dpi/elfloader.o'), *map(str, UVM), '-l', 'comp.vcs.log']


def check_config(path):
    lines = Path(path).read_text().splitlines()
    require(all(line.count('=') == 1 for line in lines), 'Malformed simulator.conf')
    data = dict(line.split('=') for line in lines)
    wanted = dict(schema_version='2', config='default', nr_lanes='4', vlen='1024', qbs='1',
                  qbs_vrf_continuation='1', akv='0', akv_v2='1', qbs_enabled='1', akv_enabled='1',
                  akv_v2_enabled='1', verify_axi_delay='0', store_b_ab_baseline='0',
                  sim_l2_mb='16', sim_l2_bytes='16777216')
    require(len(lines) == len(data) and data == wanted, 'Wrong/duplicate simulator configuration')
    return data


def load_common():
    path = ROOT / 'verification/akv/reader_fault_gate/executor_common.py'
    spec = importlib.util.spec_from_file_location('canonical_soc_compile_contract', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def tool_paths():
    result = {}
    for name in ('make', 'vcs', 'python3', 'git', 'bash', 'gcc', 'g++'):
        candidate = '/usr/bin/' + name if name in ('gcc', 'g++') else shutil.which(name)
        require(candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK), 'Missing tool: ' + name)
        result[name] = Path(candidate).absolute()
    require(result['python3'].resolve() == Path(sys.executable).resolve(), 'Make/worker Python mismatch')
    require(digest(result['vcs']) == '0735e4b82ff98dd957d5839ea15dc9fcfd9466b84e6f4ccc30d76bc2c1b96287',
            'VCS differs from accepted compiler')
    return result


def auxiliary_inputs(tools):
    paths = [PLAN, PLAN.parent / 'coherent.patch', OLD_LIST, ROOT / 'hardware/bender']
    paths += [p for p in HERE.iterdir() if p.suffix in ('.py', '.md')]
    paths += [p for path in tools.values() for p in (path, path.resolve())]
    paths += [ROOT / n for n in LOCKED]
    paths += list((ROOT / 'hardware/deps').rglob('Bender.yml'))
    for name in ('install/verilator/share/verilator/include/vltstd', 'install/riscv-isa-sim/include'):
        directory = ROOT / name
        require(directory.is_dir(), 'Missing installed DPI headers: ' + name)
        paths += [p for p in directory.rglob('*') if p.is_file() and p.suffix in ('.h', '.hpp')]
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name and Path(name).resolve().is_relative_to(ROOT):
            paths.append(Path(name).resolve())
    return {str(p): digest(p) for p in paths}


def run(args):
    require(type(args.timeout) is int and 1 <= args.timeout <= 7200, 'Compile bound must be 1..7200 seconds')
    promoted = guard()  # Must precede output creation, tool discovery or any subprocess.
    tools = tool_paths()
    output = args.output.absolute()
    require(output == output.resolve(), 'No symlink output paths')
    command = make_command(output, tools)
    require(digest(OLD_LIST) == OLD_LIST_SHA, 'Accepted graph reference drift')
    expected = expected_graph(OLD_LIST.read_text())
    c = load_common()
    check_graph('\n'.join(expected), expected, c.SOC_REPEAT_HASHES)
    output.mkdir(parents=True)
    owner = c.hand.Execution(output)
    owner.state.update(source_root=str(ROOT), canonical=True, execution='NOT_RUN', timeout_seconds=args.timeout)
    owner.save()
    for key in ('MAKEFLAGS', 'MFLAGS', 'MAKEFILES', 'GNUMAKEFLAGS', 'GCC_EXEC_PREFIX', 'COMPILER_PATH',
                'LIBRARY_PATH', 'CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'LD_PRELOAD'):
        owner.env.pop(key, None)
    owner.env['PATH'] = ':'.join(dict.fromkeys([str(p.parent) for p in tools.values()] + ['/usr/bin', '/bin']))
    owner.env['PYTHONDONTWRITEBYTECODE'] = '1'
    owner.env['PYTHONPATH'] = str(ROOT / 'verification')
    owner.env['CCACHE_DISABLE'] = '1'
    # Use the established process-group cleanup with direct foreground ownership.
    def interrupted(sig, _frame):
        raise InterruptedError(f'Signal {sig}')
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    try:
        expected_list = output / 'expected-sources.f'
        expected_list.write_text('\n'.join(expected) + '\n')
        graph = c.latency.tools.collect(expected_list, ROOT, list(UVM))
        pins = {row['path']: row['sha256'] for row in graph}
        pins.update(auxiliary_inputs(tools))
        pins.update(c.s.hashes([c.SOC_COMPILE_PRIOR, c.SOC_COMPILE_PRIOR.parent / 'vcs_source_manifest.json']))
        pins.update({str(ROOT / row['target']): row['after_sha256'] for row in promoted['files']})
        c.save(output / 'source-pins.json', pins)
        pinsha = digest(output / 'source-pins.json')
        c.save(output / 'planned-command.json', command)

        def identity():
            guard()
            verify(pins)
            require(digest(output / 'source-pins.json') == pinsha, 'Receipt changed')
            require(c.latency.tools.collect(expected_list, ROOT, list(UVM)) == graph, 'Source/header inventory changed')
            require(auxiliary_inputs(tools).items() <= pins.items(), 'Tool/header/metadata inventory changed')

        identity()
        if not args.execute:
            state = 'CANONICAL_SOC_PREFLIGHT_NOT_COMPILED'
            result = dict(state=state, source_pins_sha256=pinsha, execution='NOT_RUN', canonical=True)
        else:
            owner.execute(command, output / 'make.log', args.timeout, 'COMPILE')
            identity()
            sim = output / 'sim'
            filelist = output / 'hardware-build/vcs/bender_script_default'
            check_graph(filelist.read_text(), expected, c.SOC_REPEAT_HASHES)
            config = check_config(sim / 'simulator.conf')
            manifest = read(sim / 'vcs_source_manifest.json')
            extras = [output / 'hardware-build/work-dpi/elfloader.o', *UVM]
            require(manifest.get('repo_root') == str(ROOT) and manifest.get('filelist') == str(filelist) and
                    manifest.get('extra_sources') == list(map(str, extras)) and manifest.get('schema_version') == 1,
                    'Noncanonical/wrong generated source manifest')
            actual = c.latency.tools.collect(filelist, ROOT, extras)
            require(manifest['files'] == actual, 'Generated source manifest drift')
            for row in actual:
                if row['path'] not in (str(filelist), str(extras[0])):
                    require(pins.get(row['path']) == row['sha256'], 'Compile input not pinned before make')
            lint = c.check_soc_compile((sim / 'comp.vcs.log').read_text(), 0, expected_vcs(output, tools['vcs']), ROOT)
            require((sim / 'simv').is_file(), 'Compiler did not produce simv')
            image = c.s.hashes(c.s.image_files(sim / 'simv'))
            require(str(sim / 'simv') in image and str(sim / 'simulator.conf') in image and
                    str(sim / 'vcs_source_manifest.json') in image, 'Incomplete image inventory')
            identity()
            c.save(output / 'image-pins.json', image)
            artifacts = c.s.hashes([output / 'make.log', output / 'make.command.json',
                output / 'source-pins.json', output / 'planned-command.json', output / 'image-pins.json',
                filelist, *extras[:1], output / 'hardware-build/work-dpi/ara_dpi.so', sim / 'comp.vcs.log'])
            artifacts.update(image)
            state = 'CANONICAL_SOC_BUILT_NOT_EXECUTED'
            result = dict(state=state, schema='canonical_soc_v1', canonical=True, source_root=str(ROOT),
                plan_sha256=PLAN_SHA, source_pins_sha256=pinsha, post_pins_match=True, compiler_exit_code=0,
                simv=str(sim / 'simv'), image_pins=image, artifact_pins=artifacts, config=config, lint=lint,
                execution='NOT_RUN', simulations_launched=0, performance_measured=False,
                scope='Actual canonical Makefile compile; no old checked_soc or historical source waiver')
        c.save(output / 'result.json', result)
        owner.state['state'] = state
    except BaseException as exc:
        state = 'TIMEOUT' if isinstance(exc, subprocess.TimeoutExpired) else 'INTERRUPTED' if isinstance(exc, InterruptedError) else 'FAIL'
        owner.state.update(state=state, error=repr(exc))
        c.save(output / 'result.json', dict(owner.state))
        raise
    finally:
        owner.state['child_pid'] = None
        owner.save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=7200)
    parser.add_argument('--execute', action='store_true', help='Compile only, after actual canonical promotion')
    run(parser.parse_args())
