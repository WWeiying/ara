#!/usr/bin/env python3
"""Frozen full-processor VCS inputs, independent of dirty development sources.

Keep the accepted scalar/RVV/dependency baseline, overlay only reviewed QBS
integration, and select real generic SRAM word width at fixed byte capacity.
This is an experimental snapshot build, not canonical-source promotion.
"""
import argparse
from collections import Counter
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

from audit import digest, require, verify_pins

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
VERIFY = ROOT.parent / 'ara_dsa_signoff_integration'
RUNS = VERIFY / 'verification/out'
BASE = RUNS / 'e2e_vcs_build_20261106_01'
BASE_SHA = '32190b89a1dcf5ce0bb43a201a7b26ba23830fc753c9639837837d525a79c77c'
REVIEWED = '372797bbb'
CONFIG_COMMIT = '39f745675'
CONFIG_SHA = 'b6a0f89596caebbee87099334ffd48ac7fe5011d99e1af8f5d001625544463fc'
OVERLAY = tuple('hardware/src/vlsu/qbs/' + n + '.sv' for n in (
    'qbs_profile_decoder', 'qbs_dot_array', 'qbs_profile_engine_int', 'qbs_read_engine',
    'qbs_block_adapter', 'qbs_payload_buffer', 'qbs_compute_engine', 'qbs_engine')) + (
    'hardware/src/vlsu/qbs_akv_shared_reader.sv', 'hardware/src/vlsu/akv/akv_engine.sv',
    'hardware/src/vlsu/vlsu.sv', 'hardware/include/shared_reader_types.svh',
    'hardware/include/vlsu_shared_reader.svh')
ADDITIONS = {
    'hardware/src/vlsu/qbs_akv_shared_reader.sv': ('hardware/src/vlsu/qbs_reader_narrow_view.sv',),
    'hardware/src/vlsu/qbs/qbs_payload_sram.sv': tuple(
        'hardware/src/vlsu/qbs/' + n + '.sv' for n in
        ('qbs_weight_line_assembler', 'qbs_weight_wide_mapper', 'qbs_weight_wide_bank')),
}
NEW = tuple(p for values in ADDITIONS.values() for p in values)
TB_ANCHOR = '  localparam AxiWideDataWidth  = 64 * NrLanes/2;'
TB_REPLACEMENT = '  localparam AxiWideDataWidth  = `ARA_EXPERIMENT_AXI_DATA_WIDTH;'
FEATURE = '+define+ARA_QBS_WIDE_WEIGHT_INGRESS=1'
WARNING = r'(?m)^(?:Warning|Lint)-\[[^]]+\][\s\S]*?(?=\n\n|\Z)'


def emit(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def source_transform(relative, text):
    if relative == 'hardware/tb/ara_tb.sv':
        require(text.count(TB_ANCHOR) == 1, 'Testbench width anchor drift')
        return text.replace(TB_ANCHOR, TB_REPLACEMENT, 1)
    if relative == 'hardware/src/ara_soc.sv':
        anchor = 'endmodule : ara_soc'
        require(text.count(anchor) == 1, 'SoC probe anchor drift')
        return text.replace(anchor, '  `include "wide_soc_memory_probe.svh"\n' + anchor, 1)
    return text


def graph(text, tree, width):
    require(width in (128, 256), 'Unsupported physical width')
    lines = [s.strip() for s in text.splitlines() if s.strip()]
    require(not any('ARA_QBS_WIDE_' in s or 'ARA_EXPERIMENT_' in s or
                    'TARGET_SRAM_MC' in s or 'IDEAL_DISPATCHER' in s for s in lines),
            'Unexpected old platform/feature configuration')
    for anchor, additions in ADDITIONS.items():
        old = str(VERIFY / anchor)
        require(lines.count(old) == 1 and all(str(VERIFY / p) not in lines for p in additions),
                'Wrong original module graph')
        index = lines.index(old) + 1
        lines[index:index] = [str(VERIFY / p) for p in additions]
    mapped = []
    for line in lines:
        if line.startswith('+incdir+'):
            prefix, path = '+incdir+', Path(line[len('+incdir+'):])
        elif line.startswith('+define+'):
            mapped.append(line)
            continue
        else:
            prefix, path = '', Path(line)
        require(path.is_absolute() and path.is_relative_to(VERIFY), 'Unbound graph input: ' + line)
        mapped.append(prefix + str(tree / path.relative_to(VERIFY)))
    flags = ['+define+ARA_QBS_WIDE_MATRIX_DOT=1',
             f'+define+ARA_EXPERIMENT_AXI_DATA_WIDTH={width}']
    if width == 256: flags.append(FEATURE)
    return '\n'.join([*flags, '+incdir+' + str(tree / 'experiment'), *mapped]) + '\n'


def compile_check(text, argv, original_log, tree):
    require(not re.search(r'(?m)^Error-|\bFatal:|Assertion[^\n]*failed', text), 'Compiler error')
    require('CPU time:' in text and 'to compile' in text, 'No compiler completion record')
    header = []
    for line in text.splitlines(keepends=True):
        header.append(line)
        if not line.endswith('\\\n'): break
    header = ''.join(header)
    require(header.startswith('Command: ') and shlex.split(
        header[len('Command: '):].replace('\\\n', '')) == ['vcs', *argv[1:]],
        'Actual compiler argv differs')
    old = re.findall(WARNING, original_log)
    new = re.findall(WARNING, text)
    require(old and Counter(new) == Counter(block.replace(str(VERIFY) + '/', str(tree) + '/')
                                            for block in old), 'New/changed/missing compiler diagnostic')
    return dict(known_diagnostic_count=len(old), exact_original_diagnostics_retained=True)


def prepare(output):
    out = output.absolute()
    require(out == out.resolve() and out.is_relative_to(RUNS), 'Fresh sole-verification output required')
    out.mkdir(parents=True, exist_ok=False)
    pins, selected = {}, []
    result = dict(state='FAIL', simulations_launched=0, compiles_launched=0,
                  canonical_source_promoted=False, performance_measured=False)

    def pin(path, expected=None):
        path = Path(path).resolve(strict=True)
        sha = digest(path)
        require(expected is None or sha == expected, 'Input identity differs: ' + str(path))
        require(str(path) not in pins or pins[str(path)] == sha, 'Input drift')
        pins[str(path)] = sha

    try:
        pin(BASE / 'result.json', BASE_SHA)
        base = json.loads((BASE / 'result.json').read_text())
        require(base['state'] == 'CANONICAL_SOC_BUILT_NOT_EXECUTED' and base['post_pins_match'],
                'Wrong accepted full-processor baseline')
        pin(BASE / 'source-pins.json', base['source_pins_sha256'])
        old_pins = json.loads((BASE / 'source-pins.json').read_text())
        for name in ('sim/vcs_source_manifest.json', 'sim/comp.vcs.log'):
            path = BASE / name
            pin(path, base['artifact_pins'][str(path)])
        manifest = json.loads((BASE / 'sim/vcs_source_manifest.json').read_text())
        require(manifest['repo_root'] == str(VERIFY), 'Wrong baseline root')
        listing = Path(manifest['filelist']); pin(listing, base['artifact_pins'][str(listing)])
        rows = {row['path']: row['sha256'] for row in manifest['files']}
        require(len(rows) == len(manifest['files']) and len(rows) == 468, 'Ambiguous baseline inventory')
        for name in ('prepare_wide_soc.py', 'test_prepare_wide_soc.py', 'wide_soc_memory_probe.svh', 'audit.py'):
            pin(HERE / name)
        for name in ('wide_ingress_20261106_01', 'wide_clients_20261106_01'):
            receipt = ROOT / 'verification/performance/evidence' / name / 'result.json'
            committed = subprocess.check_output(['git', '-C', ROOT, 'show',
                REVIEWED + ':' + receipt.relative_to(ROOT).as_posix()])
            pin(receipt, hashlib.sha256(committed).hexdigest())
            accepted = json.loads(receipt.read_text()); run = Path(accepted['run'])
            pin(run / 'result.json', accepted['result_sha256'])
            pin(run / 'source-pins.json', accepted['source_pins_sha256'])
            require(json.loads((run / 'result.json').read_text())['state'] == accepted['state'],
                    'Acceptance state differs')
        reviewed = {}
        for relative in (*OVERLAY, *NEW):
            blob = subprocess.check_output(['git', '-C', ROOT, 'show', REVIEWED + ':' + relative])
            sha = hashlib.sha256(blob).hexdigest()
            pin(ROOT / relative, sha)
            reviewed[relative] = sha
        tree = out / 'source'
        for name, expected in rows.items():
            old = Path(name)
            require(old.is_relative_to(VERIFY), 'External baseline input')
            relative = old.relative_to(VERIFY).as_posix()
            if relative in OVERLAY:
                origin = ROOT / relative
                raw = origin.read_bytes()
                expected = reviewed[relative]
            elif relative == 'hardware/Makefile':
                origin = f'git:{CONFIG_COMMIT}:{relative}'
                raw = subprocess.check_output(['git', '-C', ROOT, 'show', CONFIG_COMMIT + ':' + relative])
                expected = CONFIG_SHA
            else:
                pin(old, expected)
                origin, raw = old, old.read_bytes()
            require(hashlib.sha256(raw).hexdigest() == expected, 'Selected source identity differs')
            destination = tree / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            changed = relative in ('hardware/tb/ara_tb.sv', 'hardware/src/ara_soc.sv')
            destination.write_bytes(source_transform(relative, raw.decode()).encode() if changed else raw)
            pin(destination)
            selected.append(dict(relative=relative, origin=str(origin), original_sha256=expected,
                                 snapshot_sha256=digest(destination), observation_transform=changed))
        for relative in NEW:
            destination = tree / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination); pin(destination, reviewed[relative])
            selected.append(dict(relative=relative, origin=str(ROOT / relative),
                                 original_sha256=reviewed[relative], snapshot_sha256=reviewed[relative],
                                 observation_transform=False))
        probe = tree / 'experiment/wide_soc_memory_probe.svh'
        probe.parent.mkdir(); shutil.copyfile(HERE / probe.name, probe); pin(probe)
        lists = {}
        for width in (128, 256):
            filelist = out / f'sources{width}.f'
            filelist.write_text(graph(listing.read_text(), tree, width)); pin(filelist)
            lists[str(width)] = str(filelist)
        baseline_argv = base['lint']['command_argv']
        require(baseline_argv.count('-f') == 1 and baseline_argv[-2:] == ['-l', 'comp.vcs.log'] and
                baseline_argv[baseline_argv.index('-f') + 1] == str(listing), 'Wrong baseline compiler recipe')
        # The existing DPI object is reused exactly. No dirty dependency or
        # unrelated Makefile rule can enter a direct frozen-recipe compilation.
        extra = [str(tree / Path(p).relative_to(VERIFY)) for p in manifest['extra_sources']]
        recipe = [*baseline_argv[:baseline_argv.index('-f')], '-f', '{filelist}', *extra,
                  '-l', 'comp.vcs.log']
        require(recipe[0] in old_pins and '/usr/bin/g++' in old_pins, 'Compiler tools lack baseline pins')
        pin(recipe[0], old_pins[recipe[0]])
        vcs1 = Path(recipe[0]).resolve().parent.parent / 'linux64/bin/vcs1'; pin(vcs1)
        pin(sys.executable)
        pin('/usr/bin/g++', old_pins['/usr/bin/g++'])
        (out / 'selection.json').write_text(json.dumps(selected, indent=2) + '\n'); pin(out / 'selection.json')
        verify_pins(pins)
        result.update(state='PHYSICAL_WIDE_SOC_INPUTS_PREPARED', source_root=str(tree),
            reviewed_overlay_commit=REVIEWED, baseline=str(BASE), baseline_result_sha256=BASE_SHA,
            recipe=recipe, filelists=lists, selected_count=len(selected),
            original_lanes=4, original_vlen=1024, l2_bytes=16777216, matrix_dot=1,
            widths=[128, 256], macros_selected=False, mc=0,
            limitations=['Experimental snapshot, not a canonical source promotion',
                         'Ordinary scalar/RVV/dependencies remain accepted baseline; unrelated area optimizations excluded',
                         'Generic actual SRAM only, fixed 16 MiB; no external DDR/PPA claim',
                         'No real PMP or Linux wide-path acceptance; first smoke is translation-off baremetal'])
    except BaseException as exc:
        result['error'] = repr(exc); raise
    finally:
        emit(out / 'source-pins.json', pins)
        result['source_pins_sha256'] = digest(out / 'source-pins.json')
        emit(out / 'result.json', result)


def compile_soc(prepared, expected, width, output):
    require(digest(prepared / 'result.json') == expected, 'Prepared input identity differs')
    info = json.loads((prepared / 'result.json').read_text())
    require(info['state'] == 'PHYSICAL_WIDE_SOC_INPUTS_PREPARED' and width in info['widths'],
            'Inputs not prepared for this width')
    require(digest(prepared / 'source-pins.json') == info['source_pins_sha256'], 'Input inventory differs')
    pins = json.loads((prepared / 'source-pins.json').read_text())
    verify_pins(pins)
    out = output.absolute()
    require(out == out.resolve() and out.is_relative_to(RUNS), 'Fresh sole-verification compile output')
    out.mkdir(parents=True, exist_ok=False)
    sim = out / 'sim'; sim.mkdir(); (sim / 'incremental_db').mkdir()
    argv = [word.replace('{filelist}', info['filelists'][str(width)]) for word in info['recipe']]
    result = dict(state='COMPILE', child_pid=None, width=width, prepared=str(prepared),
                  prepared_sha256=expected, source_root=info['source_root'], simulations_launched=0,
                  physical_soc_executed=False, performance_measured=False, synthesis_run=False)
    child = None

    def save():
        (out / 'status.json').write_text(json.dumps(result, indent=2) + '\n')

    try:
        for path in (prepared / 'result.json', prepared / 'source-pins.json'):
            pins[str(path)] = digest(path)
        emit(out / 'source-pins.json', pins)
        emit(out / 'compile-command.json', dict(argv=argv, cwd=str(sim), timeout_seconds=7200))
        with (out / 'compile.stdout.log').open('xb') as stream:
            child = subprocess.Popen(argv, cwd=sim, stdout=stream, stderr=subprocess.STDOUT,
                                     start_new_session=True)
            result['child_pid'] = child.pid; save()
            try:
                code = child.wait(timeout=7200)
            except BaseException:
                os.killpg(child.pid, signal.SIGKILL); child.wait(); raise
        result['child_pid'] = None
        require(code == 0, 'Full processor compile failed')
        lint = compile_check((sim / 'comp.vcs.log').read_text(), argv,
                             (BASE / 'sim/comp.vcs.log').read_text(), Path(info['source_root']))
        image = sim / 'simv'
        images = [image, *sorted((sim / 'simv.daidir').rglob('*.so'))]
        require(len(images) > 1 and image.is_file(), 'Missing complete executable image')
        verify_pins(pins)
        config = dict(json.loads((BASE / 'result.json').read_text())['config'], qbs_matrix_dot='1',
                      sim_axi_data_width=str(width), qbs_wide_weight_ingress=str(int(width == 256)))
        (sim / 'simulator.conf').write_text(''.join(k + '=' + v + '\n' for k, v in sorted(config.items())))
        result.update(state='PHYSICAL_WIDE_SOC_BUILT_NOT_EXECUTED', compiler_exit_code=code,
                      lint=lint, simv=str(image), config=config,
                      source_pins_sha256=digest(out / 'source-pins.json'),
                      image_pins={str(path): digest(path) for path in images}, post_pins_match=True)
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc)); raise
    finally:
        save()
        result['artifacts'] = {str(path): digest(path) for path in
            (out / 'compile-command.json', out / 'source-pins.json', out / 'compile.stdout.log',
             sim / 'comp.vcs.log', sim / 'simulator.conf') if path.is_file()}
        emit(out / 'result.json', result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('prepare'); p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('compile'); p.add_argument('--prepared', type=Path, required=True)
    p.add_argument('--prepared-sha', required=True); p.add_argument('--width', type=int, choices=(128, 256), required=True)
    p.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'prepare': prepare(args.output)
    else: compile_soc(args.prepared, args.prepared_sha, args.width, args.output)
