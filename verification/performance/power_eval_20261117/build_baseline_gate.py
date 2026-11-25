#!/usr/bin/env python3
"""Prepare frozen baseline GLS; admit exactly four checked RVV programs later.

Preparation, release assembly and host tests never invoke EDA. Compilation
requires the frozen worker, an immutable strict-four release, explicit consent
to reconstructed source identity, and direct ownership by the named service.
No action runs gate simulation, synthesis, SAIF conversion or power reporting.
"""

import argparse
from collections import Counter
from dataclasses import dataclass
import difflib
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
import tempfile
import time
import types
import unittest


ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
DEFAULT = OUT / 'power_gate_build_20261117_baseline_01'
RTL = OUT / 'power_rtl_20261117_baseline_01'
QUEUE = OUT / 'power_precheck_20261117_baseline_queue_01'
CAMPAIGN = QUEUE.with_name(QUEUE.name + '_runs')
N = ROOT.parent / 'ara_dsa_no_qbs_pulp_eval'
SYN = Path('backend/syn/ara_soc/v1-dc')
TB = Path('hardware/tb/ara_tb.sv')
HARNESS = Path('hardware/tb/ara_testharness.sv')
UART = Path('hardware/deps/cva6/corev_apu/tb/common/mock_uart.sv')
UNIT = 'power-gate-build-20261117-baseline-01.service'
PRIMITIVES_SHA = 'f7e5695cea9d0308e2017d3e74786a0fd78b2b45c1bcaa09f9ae8cb5033d2fb4'
MANIFEST_SHA = 'c87668595bbe5ef4d394cc20d7c7642f36fdf57538f902d7d8b41c334a2976c7'
V2_SHA = '699bc377a22a0a6f98d976b48b511c053139df97e7377c55fbc18b3500e7646a'
CHECKER_REV = 'dbe2b78817ef45b912444afcb85ad6e01a2be135'
ANCHORS = {
    RTL / 'source-pins.json': '08879790a30c834a85521e518ed24a59171b1239b3ea7a2376f4cc8825c8ff45',
    RTL / 'rtl-receipt.json': '439705d84e96d84b9c599a49841eccdbbc3fe1f16ab931f8ab8c918ed3c662c0',
    RTL / 'build.json': 'ac5242e115e3bcc70ea61483240e3ca2548151cd8c9eecb4c518151333d8c7c7',
    RTL / 'image-pins.json': 'caa2013d2df5722282ba4193b6213ec22c959381a75c92310691f85444f69d76',
    QUEUE / 'inputs/manifest.json': MANIFEST_SHA,
}
DEFINES = frozenset({
    'SAIF', 'TARGET_GATESIM', 'TARGET_SRAM_MC', 'RVV_GATESIM', 'ARA_NO_FSDB',
    'POWER_CAPTURE_EXTERNAL', 'NR_LANES=4', 'VLEN=1024', 'SIM_L2_SIZE_BYTES=1048576',
    'TARGET_CV64A6_IMAFDCV_SV39', 'ARIANE_ACCELERATOR_PORT=1',
    'COMMON_CELLS_ASSERTS_OFF', 'HPDCACHE_ASSERT_OFF', 'NO_SYNOPSYS_FF',
})
RTL_BUILT = 'RECONSTRUCTED_BASELINE_RTL_BUILT_NOT_EXECUTED'
GATE_BUILT = 'RECONSTRUCTED_BASELINE_GATE_BUILT_NOT_SIMULATED'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, data):
    with Path(path).open('x') as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write('\n')


def verify(pins):
    for path, expected in pins.items():
        require(sha(path) == expected, 'Identity drift: ' + str(path))


def primitives_path():
    frozen = Path(__file__).resolve().parent / 'build_gate_primitives.py'
    return frozen if frozen.is_file() else Path(__file__).resolve().with_name('build_gate.py')


def primitives():
    path = primitives_path()
    require(sha(path) == PRIMITIVES_SHA, 'Sealed gate primitives changed')
    # Load read-only without generating pycache or changing its all-on globals.
    module = types.ModuleType('sealed_power_gate_primitives')
    module.__file__ = str(path)
    exec(compile(path.read_text(), str(path), 'exec'), module.__dict__)
    return module


@dataclass(frozen=True)
class BaselineContext:
    rtl_image: Path = RTL
    source_root: Path = RTL / 'source'
    original_root: Path = N
    revision: str = 'd0c7d62d3be3c6c05f320252b95d65f0ca0a323a'
    historical_byte_identity: str = 'UNPROVEN'
    netlist_sha256: str = '113e08053dab899b1e2a646e936218068d8cfbffb80c26b0b3a92a5d21364d7b'
    ddc_sha256: str = '2eea3c4a4ac10dcaac37d62514d1d6dcc43f916c93b48ecb11838cf51f3e45d5'

    def artifact(self, name):
        return self.source_root / SYN / 'outputs' / name

    def receipt(self):
        return dict(rtl_image=str(self.rtl_image), frozen_source_root=str(self.source_root),
                    original_source_root=str(self.original_root), revision=self.revision,
                    historical_byte_identity=self.historical_byte_identity,
                    netlist_sha256=self.netlist_sha256, ddc_sha256=self.ddc_sha256,
                    historically_sealed=False, source_reconstructed=True)


def validate_context(ctx):
    verify(ANCHORS)
    pins = read(ctx.rtl_image / 'source-pins.json')
    verify(pins)
    receipt, build = read(ctx.rtl_image / 'rtl-receipt.json'), read(ctx.rtl_image / 'build.json')
    image = read(ctx.rtl_image / 'image-pins.json')
    require(receipt['historical_byte_identity'] == ctx.historical_byte_identity == 'UNPROVEN'
            and receipt['reconstructed'] is True and receipt['historically_sealed'] is False
            and receipt['revision'] == ctx.revision and receipt['rtl_design_bytes_changed'] == 0,
            'Wrong reconstructed baseline receipt')
    require(receipt['decoder']['gpr_count'] == 32 and not receipt['decoder']['custom_qbs_akv_decode'],
            'Ordinary 32-register RVV baseline required')
    require(build['state'] == RTL_BUILT and build['image_pins'] == image
            and build['rtl_receipt_sha256'] == sha(ctx.rtl_image / 'rtl-receipt.json'), 'Wrong RTL build')
    verify(image)
    verify({ctx.artifact('ara_soc_dc.v'): ctx.netlist_sha256,
            ctx.artifact('ara_soc_dc.ddc'): ctx.ddc_sha256})
    config = read(ctx.rtl_image / 'plan.json')['configuration']
    require(config['nr_lanes'] == 4 and config['vlen'] == 1024 and config['sim_l2_bytes'] == 1048576
            and config['qbs_enabled'] == config['akv_enabled'] == config['akv_v2_enabled'] == 0,
            'Wrong baseline RTL configuration')
    return pins, image


def adapt_tb(g, text, banks):
    text = g.project_tb(text, DEFINES)
    start = text.index('  logic [63:0] wall_cycle;')
    end = text.index('  /*********\n   *  DUT', start)
    text = text[:start] + text[end:]
    # The old TB retains a commented-out alternate preload implementation.
    # Remove comments before anchoring executable preload statements.
    text = g.uncomment(text)
    start = text.index('  initial begin\n    string testcase;')
    end = text.index('  logic [63:0] exit;', start)
    text = (text[:start] + '`ifndef POWER_CAPTURE_EXTERNAL\n' + text[start:end]
            + '`endif\n' + text[end:])
    for i, instance in enumerate(banks):
        text = g.replace_once(text, f'dut.i_ara_soc.gen_dram[{i} ].i_dram.preloadData(temp_file);',
                              f'dut.i_ara_soc.{instance}.preloadData(temp_file);')
    text = g.replace_once(text, '        buffer = new[nwords * AxiWideBeWidth];',
        '        if (address < DRAMAddrBase || address >= DRAMAddrBase + L2SizeBytes ||\n'
        '            length > DRAMAddrBase + L2SizeBytes - address ||\n'
        '            address % AxiWideBeWidth != 0)\n'
        '          $fatal(1, "ELF section outside exact 1 MiB or unaligned");\n'
        '        buffer = new[nwords * AxiWideBeWidth];')
    text = g.replace_once(text,
        '                $display("Cannot initialize address %x, which doesn\'t fall into the L2 region.", word_addr);',
        '                $fatal(1, "ELF address %x outside exact 1 MiB gate memory", word_addr);')
    text = g.replace_once(text, 'default: $display("Invalid bank index: %0d", bank_index);',
                          'default: $fatal(1, "Invalid bank index: %0d", bank_index);')
    active = g.uncomment(g.project_tb(text, DEFINES))
    require('i_system' not in active and 'gen_dram[' not in active and '$dumpvars' not in active
            and '$fsdb' not in active and 'i_dram.init_val' not in active,
            'RTL hierarchy or uncontrolled dumping survived baseline TB projection')
    require(active.count('.preloadData(temp_file)') == 8, 'Exactly eight macro preload tasks required')
    return text


def adapt_harness(g, text):
    text = g.project_tb(text, DEFINES)
    text, count = re.subn(r'  ara_soc #\([\s\S]*?\n  \) i_ara_soc', '  ara_soc i_ara_soc', text)
    require(count == 1 and 'i_system' not in g.uncomment(text), 'Passive mapped harness projection failed')
    return text


def library_paths(text):
    # This inventory accepts literal library assignments only, never evaluates Tcl.
    paths = [Path(m[1]) for m in re.finditer(r'(?m)^set\s+\w+\s+(/[^\s"{}]+\.db)\s*$', text)]
    require(len(paths) == len(set(paths)) == 9, 'Expected four standard-cell and five SRAM databases')
    require(all('tt0p9v25c' in p.name for p in paths), 'Wrong library PVT')
    return paths


def expected_cases(manifest):
    cases = manifest['cases']
    ids = [c['id'] for c in cases]
    require(len(cases) == 4 and len(set(ids)) == 4 and all('rvv' in n for n in ids),
            'Exactly four distinct RVV programs required')
    require(all(not c.get('plusargs') for c in cases), 'Unexpected runtime configuration overrides')
    return {c['id']: c for c in cases}


def prepare(out, ctx):
    require(not out.exists(), 'Fresh owned output required; no retry/overwrite')
    pins, _ = validate_context(ctx)
    g = primitives()
    manifest = read(QUEUE / 'inputs/manifest.json')
    expected_cases(manifest)
    flist = ctx.source_root / 'backend/flist/ara_soc_dc.f'
    design = list(dict.fromkeys(ctx.source_root / Path(l.strip()).relative_to(ctx.original_root)
                               for l in flist.read_text().splitlines() if l.strip().startswith('/')))
    require(all(str(p) in pins for p in design), 'Unpinned baseline filelist input')
    texts = {p: p.read_text() for p in design}
    packages = g.package_closure(design, texts)
    net = ctx.artifact('ara_soc_dc.v')
    net_names, instances, banks = g.netlist_inventory(net)
    require(len(net_names) == len(set(net_names)) and net_names.count('ara_soc') == 1,
            'Duplicate mapped modules')
    require(banks == [f'gen_dram_{i}__i_dram' for i in range(8)], 'Unexpected flat macro names')
    external = set(instances) - set(net_names)
    env = ctx.source_root / SYN / 'global_scripts/synopsys_dc.setup.env'
    synth_log = (ctx.source_root / SYN / 'run/dc.out.4').read_text()
    dbs = library_paths(env.read_text())
    require(all(str(p) in synth_log for p in dbs), 'Library not corroborated by final synthesis log')
    libraries, library_pins = [], {}
    for db in dbs:
        model = g.resolve_model(db)
        library_pins[str(db)] = sha(db)
        names = g.library_declarations(model)
        if set(names) & external:
            libraries.append(dict(db=str(db), db_sha256=library_pins[str(db)], model=str(model),
                                  model_sha256=sha(model), declarations=names))
    require(libraries, 'No mapped libraries')
    model_text = g.unique_models(libraries, external)
    all_names = [*net_names, *(n for lib in libraries for n in lib['compiled_declarations'])]
    require(not [n for n, count in Counter(all_names).items() if count > 1], 'Duplicate library cells')
    require(not external - set(all_names), 'Unresolved mapped cells: ' + repr(sorted(external - set(all_names))))
    out.mkdir()
    for name in ('source', 'inputs', 'models', 'sim/incremental_db', 'logs', 'vcd'):
        (out / name).mkdir(parents=True)
    copied = {}

    def copy(src, dest, expected):
        verify({str(src): expected})
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        verify({str(src): expected, str(dest): expected})
        copied[str(dest.relative_to(out))] = dict(origin=str(src), sha256=expected)
        return dest

    paths = [copy(p, out / 'source' / p.relative_to(ctx.source_root), pins[str(p)]) for p in packages]
    for name, expected in pins.items():
        path = Path(name)
        if path.is_relative_to(ctx.source_root) and path.suffix in ('.svh', '.vh', '.h'):
            copy(path, out / 'source' / path.relative_to(ctx.source_root), expected)
    for rel in (TB, HARNESS, UART):
        path = ctx.source_root / rel
        raw = copy(path, out / 'inputs' / rel.name, pins[str(path)]).read_text()
        derived = adapt_tb(g, raw, banks) if rel == TB else adapt_harness(g, raw) if rel == HARNESS else raw
        dest = out / 'source' / rel.name
        dest.write_text(derived)
        paths.append(dest)
        if raw != derived:
            (out / 'inputs' / (rel.name + '.diff')).write_text(''.join(difflib.unified_diff(
                raw.splitlines(True), derived.splitlines(True), fromfile=str(path), tofile=str(dest))))
    paths.append(copy(net, out / 'source/ara_soc_dc.v', ctx.netlist_sha256))
    copy(ctx.artifact('ara_soc_dc.ddc'), out / 'inputs/ara_soc_dc.ddc', ctx.ddc_sha256)
    for lib in libraries:
        model = Path(lib['model'])
        copy(model, out / 'inputs/models' / model.name, lib['model_sha256'])
        dest = out / 'models' / model.name
        dest.write_text(model_text[str(model)])
        require(g.declarations(dest.read_text()) == lib['compiled_declarations'], 'Model filtering mismatch')
        lib.update(frozen_model=str(dest), compiled_model_sha256=sha(dest))
    copy(env, out / 'inputs/synthesis-library.env', pins[str(env)])
    copy(flist, out / 'inputs/baseline-synthesis.f', pins[str(flist)])
    copy(ctx.rtl_image / 'rtl-receipt.json', out / 'inputs/baseline-rtl-receipt.json',
         ANCHORS[ctx.rtl_image / 'rtl-receipt.json'])
    copy(QUEUE / 'inputs/manifest.json', out / 'inputs/precheck-manifest.json', MANIFEST_SHA)
    copy(primitives_path(), out / 'inputs/build_gate_primitives.py', PRIMITIVES_SHA)
    copy(Path(__file__).resolve(), out / 'inputs/build_baseline_gate.py', sha(__file__))
    dpi = copy(ctx.rtl_image / 'elfloader.o', out / 'elfloader.o', pins[str(ctx.rtl_image / 'elfloader.o')])
    copy(ctx.rtl_image / 'plan.json', out / 'inputs/rtl-plan.json', pins[str(ctx.rtl_image / 'plan.json')])
    controller = out / 'source/power_capture.sv'
    controller.write_text(g.ROI)
    paths.append(controller)
    incdirs = []
    for line in flist.read_text().splitlines():
        if line.startswith('+incdir+'):
            for name in line[8:].split('+'):
                dest = out / 'source' / Path(name).relative_to(ctx.original_root)
                if dest.is_dir():
                    incdirs.append(dest)
    for path in paths:
        if path.name == 'ara_soc_dc.v':
            continue
        for name in re.findall(r'`include\s+"([^"]+)"', g.uncomment(path.read_text())):
            require(any((d / name).is_file() for d in [path.parent, *incdirs]), 'Missing frozen include: ' + name)
    counts = Counter(n for p in paths for n in (net_names if p.name == 'ara_soc_dc.v'
                                               else g.declarations(p.read_text())))
    require(not any(v > 1 for v in counts.values()), 'Duplicate package/support definition')
    require(not set(counts) & {n for lib in libraries for n in lib['compiled_declarations']},
            'Package/support and library collision')
    require(not any(re.search(r'QBS|AKV|IDEAL|SHARED', d) for d in DEFINES), 'Wrong gate defines')
    (out / 'sources.f').write_text('\n'.join(
        ['+define+' + d for d in sorted(DEFINES)] +
        ['+incdir+' + str(p) for p in dict.fromkeys(incdirs)] + list(map(str, paths))) + '\n')
    rtl_plan = read(ctx.rtl_image / 'plan.json')
    command = [rtl_plan['command'][0], '-full64', '-sverilog', '+v2k', '-j4',
               '-Mlib=./incremental_db', '-Mupdate', '-debug_access+all', '+nospecify', '+notimingchecks',
               '-timescale=1ns/100fs', '-top', 'ara_tb', '-top', 'power_capture',
               '-f', str(out / 'sources.f'), str(dpi)]
    for lib in libraries:
        command.extend(['-v', lib['frozen_model']])
    command.extend(['-o', str(out / 'sim/simv'), '-l', str(out / 'logs/compile.vcs.log')])
    receipt = dict(schema='power-baseline-gate-static-v1', state='PREPARED_NOT_COMPILED',
        baseline_context=ctx.receipt(), rtl_image=str(ctx.rtl_image), revision=ctx.revision,
        historical_byte_identity='UNPROVEN', netlist_sha256=ctx.netlist_sha256, ddc_sha256=ctx.ddc_sha256,
        memory=dict(bytes=1048576, bank_words=8192, bank_width=128, instances=banks,
                    hier_prefix='ara_tb.dut.i_ara_soc', preload_task='preloadData'),
        packages=[str(p.relative_to(ctx.source_root)) for p in packages], libraries=libraries,
        library_database_hashes=library_pins, historical_library_bytes='UNPROVEN',
        library_selection='Literal paths from frozen baseline synthesis environment, corroborated by dc.out.4',
        copied_inputs=copied, direct_sources=len(paths), mapped_modules=len(net_names),
        external_cell_types=len(external), duplicate_definitions=[], unresolved_mapped_cell_types=[],
        roi_controller_sha256=sha(controller), roi_source_helper_sha256=PRIMITIVES_SHA,
        compile_authorized=False, eda_invoked=False, rtl_prechecks_verified=False,
        precheck_admission='STRICT_FOUR_RVV_PENDING', admitted_cases=[],
        adaptations=['Project corresponding baseline TB with SAIF/TARGET_GATESIM; no newer RTL types',
                     'Remove RTL-only lane history and use passive parameterless mapped SoC harness',
                     'Select actual eight flat macro preload names with fail-closed ELF bounds',
                     'External proper-state VCD start; mandatory finite watchdog and bounded ROI',
                     'Filter unused cells and coalesce identical UDP definitions; retained bodies unchanged'],
        timing_warning='ZERO-DELAY LOGIC GLS: +nospecify +notimingchecks, no SDF. '
                       'Behavioral cell/SRAM procedural delays may remain. Not timing closure or glitch-accurate power.',
        limitations=['Historical RTL source byte identity remains UNPROVEN; no fake all-on DC identity.',
                     'Database and model bytes hashed now, not proven to be original synthesis-time bytes.',
                     'No RTL commit/vector/protocol monitors are compiled into mapped GLS.',
                     'All four independent RTL numerical/protocol prechecks must pass before gate compilation.',
                     'Window completion task_pass=0 is activity only, not firmware completion or equivalence.',
                     'ROI uses post-reset gate clock edges; actual boundaries need gate validation.',
                     'SRAM procedural timing and warnings require separate gate smoke.',
                     'DPI read_section byte/void declaration discrepancy inherited; return unused.'])
    save(out / 'gate-receipt.json', receipt)
    save(out / 'plan.json', dict(state='PREPARED_WAITING_STRICT_FOUR_RVV_NOT_AUTHORIZED',
        baseline_context=ctx.receipt(), compile_argv_template_not_authorized=command,
        cwd=str(out / 'sim'), environment_source=str(out / 'inputs/rtl-plan.json'),
        compile_timeout_seconds=7200, max_host_jobs=4, automatic_retry=False, compilation_authorized=False,
        release=str(out / 'release.json'), campaign=str(CAMPAIGN), queue=str(QUEUE),
        runtime=dict(required=['+PRELOAD=/absolute/prechecked.elf', '+GATE_MAX_CYCLES=N'],
                     optional_vcd=['+GATE_VCD=/absolute/window.vcd', '+GATE_ROI_FIRST=N',
                                   '+GATE_ROI_LAST=M', '+GATE_STOP_AFTER_CAPTURE'],
                     clock_ns=1, sdf=False, simulation_started=False),
        prerequisites=['Original complete four-case baseline queue PASS; no subset or recovered worker admission',
                       'Exact ELF, image, numeric and protocol identities must remain unchanged',
                       'Explicit --acknowledge-reconstruction and --authorize-compile under direct service ownership']))
    save(out / 'release-template.json', dict(schema='power-baseline-gate-release-v1',
        state='DRAFT_NOT_ADMITTED', baseline_context=ctx.receipt(), image=str(ctx.rtl_image),
        campaign=str(CAMPAIGN), required_case_ids=list(expected_cases(manifest)),
        instructions='Use frozen worker release --acknowledge-reconstruction after queue finish. '
                     'Only all four original PASS rows with complete numeric/protocol evidence are admitted. '
                     'The action writes immutable release/admission/pins and ready-command.json; it never compiles.'))
    save(out / 'commands-ready.json', dict(
        release=['/usr/bin/python3', '-B', str(out / 'inputs/build_baseline_gate.py'), 'release',
                 '--output', str(out), '--acknowledge-reconstruction'],
        check=['/usr/bin/python3', '-B', str(out / 'inputs/build_baseline_gate.py'), 'check', '--output', str(out)],
        compile_service='ready-command.json is generated only by successful strict-four release', launched=False))
    frozen_pins = {str(p): sha(p) for p in out.rglob('*') if p.is_file()}
    frozen_pins.update({str(p): h for p, h in ANCHORS.items()})
    save(out / 'source-pins.json', frozen_pins)
    verify(frozen_pins)
    save(out / 'status.json', dict(state='PREPARED_NOT_COMPILED', jobs_launched=0,
                                  historical_byte_identity='UNPROVEN', rtl_prechecks_verified=False))
    return receipt


def reference(ref):
    require(isinstance(ref, dict) and set(ref) == {'path', 'sha256'}, 'Explicit path/hash reference required')
    path = Path(ref['path'])
    require(path.is_absolute() and path == path.resolve() and
            re.fullmatch(r'[0-9a-f]{64}', ref['sha256']), 'Invalid reference')
    verify({str(path): ref['sha256']})
    return path


def strict_aggregate(data, expected, image):
    require(data.get('state') == 'PASS' and data.get('pin_error') is None
            and data.get('rtl_precheck_only') is True and data.get('image') == str(image)
            and data.get('image_state') == RTL_BUILT, 'Complete reconstructed RTL aggregate PASS required')
    rows = data.get('cases', [])
    require(len(rows) == 4 and {r['id'] for r in rows} == set(expected)
            and len({r['id'] for r in rows}) == 4, 'Strict four-case aggregate mismatch')
    for row in rows:
        require(row['state'] == 'PASS' and row.get('independent_protocol_checked') is True
                and row.get('image_state') == RTL_BUILT and row.get('numeric', {}).get('state') == 'PASS'
                and row['elf_sha256'] == expected[row['id']]['elf_sha256'], 'Original checked PASS required')
    return {r['id']: r for r in rows}


def protocol_gate(proof, case, work, image, rtl_image):
    runtime = {k: v for k, v in image.items() if k == str(rtl_image / 'sim/simv') or k.endswith('.so')}
    actual = {str(rtl_image / 'sim/simv')} | {str(p) for p in (rtl_image / 'sim/simv.daidir').rglob('*.so')}
    require(set(runtime) == actual and proof['status'] == 'PASS' and proof['issues'] == []
            and proof['sim_image_sha256'] == runtime, 'Protocol PASS and complete runtime image inventory required')
    for field, expected in dict(elf_sha256=case['elf_sha256'], simv_sha256=image[str(rtl_image / 'sim/simv')],
                               log_sha256=sha(work / 'run.vcs.log'),
                               vector_trace_sha256=sha(work / 'vector.csv')).items():
        require(proof[field] == expected, 'Protocol identity mismatch: ' + field)
    counts = proof['contract_counts']
    require(all(counts[k] == 0 for k in ('exceptions', 'protocol_errors', 'outstanding'))
            and counts['requests'] == counts['responses'] > 0, 'Undrained contract')
    for kind, a, b in (('uvm', 'requests', 'responses'), ('backend', 'allocations', 'completions')):
        count = proof[kind + '_counts']
        require(count[a] == count[b] > 0 and count['aborted'] == 0, 'Incomplete protocol/backend work')
    ar, aw = proof['axi_read_counts'], proof['axi_write_counts']
    require(ar['pending'] == aw['pending'] == ar['aborted'] == aw['aborted'] == 0
            and ar['ar'] == ar['completed'] > 0 and aw['aw'] == aw['b'] == aw['matched'] > 0,
            'Incomplete AXI reads/writes')
    require(all(proof[k] > 0 for k in ('contract_event_count', 'uvm_event_count',
                                     'uvm_backend_event_count', 'vector_backend_event_count')),
            'Missing independent trace events')


def inspect_release(out, ctx):
    _, image = validate_context(ctx)
    verify(read(out / 'source-pins.json'))
    manifest = read(out / 'inputs/precheck-manifest.json')
    expected = expected_cases(manifest)
    require(sha(out / 'inputs/precheck-manifest.json') == MANIFEST_SHA, 'Precheck manifest drift')
    queue_result = read(QUEUE / 'result.json')
    require(queue_result['state'] == 'RTL_PRECHECKS_PASS' and queue_result['campaign'] == str(CAMPAIGN),
            'Queued controller has not completed all four prechecks')
    verify(read(QUEUE / 'source-pins.json'))
    plan, aggregate = read(CAMPAIGN / 'plan.json'), read(CAMPAIGN / 'result.json')
    require(plan['cases'] == manifest['cases'] and plan['image'] == str(ctx.rtl_image)
            and plan['scope'] == manifest['scope'] and 1 <= plan['parallel'] <= 4,
            'Queued precheck plan/configuration mismatch')
    require(plan['protocol_checker_commit'] == CHECKER_REV
            and plan['protocol_pythonpath'] == str(CAMPAIGN / 'inputs/checker/verification')
            and plan['accepted_image_states'] == ['DC_MATCHED_RTL_BUILT_NOT_EXECUTED', RTL_BUILT],
            'Unknown protocol checker configuration')
    pins = read(CAMPAIGN / 'source-pins.json')
    verify(pins)
    require(pins.get(str(CAMPAIGN / 'inputs/precheck_v2.py')) == V2_SHA
            == sha(CAMPAIGN / 'inputs/precheck_v2.py'), 'Unknown precheck worker')
    rows = strict_aggregate(aggregate, expected, ctx.rtl_image)
    require(aggregate['scope'] == manifest['scope'], 'Aggregate scope drift')
    evidence = {str(p): sha(p) for p in (QUEUE / 'result.json', QUEUE / 'source-pins.json',
                                       CAMPAIGN / 'plan.json', CAMPAIGN / 'result.json',
                                       CAMPAIGN / 'source-pins.json')}
    entries = []
    for case in manifest['cases']:
        work = CAMPAIGN / 'runs' / case['id']
        row, numeric, proof = (read(work / name) for name in ('result.json', 'numerical.json', 'protocol.json'))
        require(row == rows[case['id']] and row['scope'] == manifest['scope']
                and row['numeric'] == numeric and numeric['state'] == 'PASS', 'Per-case/aggregate/numeric mismatch')
        require(pins.get(case['elf']) == case['elf_sha256'], 'ELF not pinned by precheck')
        verify({case['elf']: case['elf_sha256']})
        log = (work / 'run.vcs.log').read_text()
        require('Core Test *** SUCCESS ***' in log and not re.search(
            r'(?mi)^\s*(?:Error[-:]|Fatal:)|Assertion failed|\bFAILED\b', log), 'RTL completion/error gate')
        require((work / 'commit.csv').stat().st_size > 0 and (work / 'vector.csv').stat().st_size > 0,
                'Missing commit/vector traces')
        protocol_gate(proof, case, work, image, ctx.rtl_image)
        refs = {}
        for name in ('result.json', 'numerical.json', 'protocol.json', 'run.vcs.log', 'vector.csv', 'commit.csv'):
            path = work / name
            refs[name] = dict(path=str(path), sha256=sha(path))
            evidence[str(path)] = refs[name]['sha256']
        evidence[case['elf']] = case['elf_sha256']
        entries.append(dict(id=case['id'], elf=dict(path=case['elf'], sha256=case['elf_sha256']),
                            original_worker_state='PASS', evidence=refs))
    verify(pins)
    verify(image)
    verify(evidence)
    return dict(schema='power-baseline-gate-release-v1', state='STRICT_FOUR_RVV_PASS_NOT_COMPILE_AUTHORIZATION',
                baseline_context=ctx.receipt(), historical_byte_identity='UNPROVEN',
                reconstruction_acknowledged=True, image=str(ctx.rtl_image), campaign=str(CAMPAIGN),
                manifest_sha256=MANIFEST_SHA, cases=entries, evidence_pins=evidence,
                original_aggregates_modified=False, compile_authorized=False)


def service_command(out, release_sha):
    worker = ['/usr/bin/python3', '-B', str(out / 'inputs/build_baseline_gate.py'), 'execute',
              '--output', str(out), '--release', str(out / 'release.json'), '--release-sha256', release_sha,
              '--acknowledge-reconstruction', '--authorize-compile']
    return ['/usr/bin/systemd-run', '--user', '--unit=' + UNIT, '--property=Type=exec',
            '--property=KillMode=control-group', '--property=CPUQuota=400%',
            '--property=RuntimeMaxSec=7800', '--property=TimeoutStopSec=20',
            '--property=StandardOutput=append:' + str(out / 'service.stdout.log'),
            '--property=StandardError=append:' + str(out / 'service.stderr.log'), *worker]


def make_release(out, ctx, acknowledged):
    require(acknowledged, 'Explicit --acknowledge-reconstruction required')
    require(Path(__file__).resolve() == out / 'inputs/build_baseline_gate.py', 'Use frozen worker')
    require(not any((out / name).exists() for name in ('release.json', 'release-pins.json', 'attempt.json')),
            'Release/attempt already exists; preserve it')
    data = inspect_release(out, ctx)
    save(out / 'release.json', data)
    release_sha = sha(out / 'release.json')
    command = service_command(out, release_sha)
    save(out / 'ready-command.json', dict(service=command, shell=shlex.join(command), launched=False,
                                        release_sha256=release_sha, simulation_command=None))
    save(out / 'release-admission.json', dict(state=data['state'], cases=[c['id'] for c in data['cases']],
        release_sha256=release_sha, historical_byte_identity='UNPROVEN', compile_authorized=False))
    pins = dict(data['evidence_pins'])
    pins.update({str(out / name): sha(out / name) for name in
                 ('release.json', 'ready-command.json', 'release-admission.json')})
    save(out / 'release-pins.json', pins)
    verify(pins)
    return dict(state=data['state'], release=str(out / 'release.json'), release_sha256=release_sha,
                ready_command=str(out / 'ready-command.json'), compile_launched=False)


def check_release(out, ctx, path, expected):
    require(path == out / 'release.json', 'Only owned strict-four release is accepted')
    reference(dict(path=str(path), sha256=expected))
    verify(read(out / 'release-pins.json'))
    release = read(path)
    require(release == inspect_release(out, ctx), 'Release no longer matches complete original evidence')
    return release


def execute(out, ctx, authorized, acknowledged, release, release_sha):
    require(authorized and acknowledged, 'Explicit compile authorization and reconstruction acknowledgement required')
    require(Path(__file__).resolve() == out / 'inputs/build_baseline_gate.py', 'Use frozen worker')
    require(not (out / 'attempt.json').exists(), 'No retry; preserve failed evidence')
    verify(read(out / 'source-pins.json'))
    admission = check_release(out, ctx, release, release_sha)
    group = Path('/proc/self/cgroup').read_text()
    owner = subprocess.check_output(['/usr/bin/systemctl', '--user', 'show', UNIT,
                                     '-p', 'MainPID', '--value'], text=True).strip()
    require('/' + UNIT in group and owner == str(os.getpid()), 'Direct named service ownership required')
    save(out / 'attempt.json', dict(pid=os.getpid(), cgroup=group, started=time.time(),
                                   release_sha256=release_sha, admitted_cases=[c['id'] for c in admission['cases']]))
    plan = read(out / 'plan.json')
    report = dict(state='FAIL', gls_runs=0, baseline_context=ctx.receipt(), historical_byte_identity='UNPROVEN',
                  timing_acceptance=False, power_acceptance=False)
    try:
        command = plan['compile_argv_template_not_authorized']
        require('-R' not in command and '-j4' in command and '+nospecify' in command
                and '+notimingchecks' in command, 'Wrong compile options')
        with (out / 'compile.console.log').open('x') as stream:
            with subprocess.Popen(command, cwd=plan['cwd'],
                                  env=read(plan['environment_source'])['environment'], stdout=stream,
                                  stderr=subprocess.STDOUT, start_new_session=True) as proc:
                try:
                    rc = proc.wait(timeout=plan['compile_timeout_seconds'])
                except BaseException:
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
                    raise
        require(rc == 0, 'VCS compile failed: ' + str(rc))
        for log in (out / 'compile.console.log', out / 'logs/compile.vcs.log'):
            require(log.is_file() and not re.search(r'(?m)^\s*(?:Error-|Fatal-|Error:|Fatal:)',
                    log.read_text(errors='replace')), 'Compile log failure: ' + str(log))
        verify(read(out / 'source-pins.json'))
        check_release(out, ctx, release, release_sha)
        image = {str(p): sha(p) for p in (out / 'sim/simv.daidir').rglob('*') if p.is_file()}
        require(image, 'Missing VCS image sidecars')
        image[str(out / 'sim/simv')] = sha(out / 'sim/simv')
        save(out / 'image-pins.json', image)
        report.update(state=GATE_BUILT, image_pins=image, release_sha256=release_sha,
                      admitted_cases=[c['id'] for c in admission['cases']])
    except Exception as exc:
        report['error'] = repr(exc)
    save(out / 'build.json', report)
    save(out / 'compile-status.json', dict(state=report['state'], finished=time.time()))
    print(json.dumps(report))
    return int(report['state'] == 'FAIL')


class HostTests(unittest.TestCase):
    def test_projection(self):
        g = primitives()
        ctx = BaselineContext()
        banks = [f'gen_dram_{i}__i_dram' for i in range(8)]
        tb = adapt_tb(g, (ctx.source_root / TB).read_text(), banks)
        harness = adapt_harness(g, (ctx.source_root / HARNESS).read_text())
        active = g.uncomment(g.project_tb(tb, DEFINES))
        self.assertEqual(active.count('.preloadData(temp_file)'), 8)
        for instance in banks:
            self.assertIn('dut.i_ara_soc.' + instance + '.preloadData', active)
        for bad in ('i_system', 'gen_dram[', '$dumpvars', '$fsdb'):
            self.assertNotIn(bad, active + g.uncomment(harness))
        self.assertNotIn('ara_soc #(', harness)
        self.assertIn('length > DRAMAddrBase + L2SizeBytes - address', active)
        self.assertIn('`ifndef POWER_CAPTURE_EXTERNAL', tb)
        self.assertTrue(all(not re.search(r'QBS|AKV|IDEAL|SHARED', d) for d in DEFINES))
        self.assertEqual(g.RTL.name, 'power_rtl_20261117_host02')
        self.assertEqual(g.DC.name, 'attempt_03')

    def test_proper_state_roi(self):
        roi = primitives().ROI
        self.assertEqual(roi.count('$dumpvars'), 1)
        self.assertIn('cycles == first_cycle', roi)
        self.assertIn('last_cycle >= max_cycles', roi)
        self.assertIn('Gate exit before ROI completion', roi)
        self.assertIn('task_pass=0', roi)
        self.assertIn('GATE_MAX_CYCLES is mandatory', roi)
        self.assertIn('GATE_STOP_AFTER_CAPTURE', roi)

    def test_context_and_libraries(self):
        ctx = BaselineContext()
        self.assertEqual(ctx.receipt()['historical_byte_identity'], 'UNPROVEN')
        self.assertNotIn('dc_attempt', ctx.receipt())
        paths = library_paths((ctx.source_root / SYN / 'global_scripts/synopsys_dc.setup.env').read_text())
        self.assertEqual(len(paths), 9)
        with self.assertRaises(ValueError):
            library_paths('source mutable.tcl')
        self.assertEqual(8 * 8192 * 128 // 8, 1048576)

    def test_strict_four(self):
        import copy
        expected = {str(i) + '_rvv': {'id': str(i) + '_rvv', 'elf_sha256': str(i) * 64} for i in range(4)}
        data = dict(state='PASS', pin_error=None, rtl_precheck_only=True, image=str(RTL), image_state=RTL_BUILT,
                    cases=[dict(id=k, state='PASS', independent_protocol_checked=True, image_state=RTL_BUILT,
                                numeric={'state': 'PASS'}, elf_sha256=v['elf_sha256']) for k, v in expected.items()])
        self.assertEqual(len(strict_aggregate(data, expected, RTL)), 4)
        mutations = []
        for field, value in (('state', 'INCOMPLETE'), ('image_state', 'DC_MATCHED_RTL_BUILT_NOT_EXECUTED'),
                             ('image', '/wrong'), ('pin_error', 'drift')):
            bad = copy.deepcopy(data)
            bad[field] = value
            mutations.append(bad)
        for state in ('FAIL', 'TIMEOUT', 'NOT_DISPATCHED_AFTER_FAILURE'):
            bad = copy.deepcopy(data)
            bad['cases'][0]['state'] = state
            mutations.append(bad)
        bad = copy.deepcopy(data)
        bad['cases'].pop()
        mutations.append(bad)
        bad = copy.deepcopy(data)
        bad['cases'][-1] = bad['cases'][0]
        mutations.append(bad)
        for bad in mutations:
            with self.assertRaises(ValueError):
                strict_aggregate(bad, expected, RTL)

    def test_models_and_authorization(self):
        g = primitives()
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / 'm.v'
            model.write_text('module used ();\nendmodule\nmodule unused ();\nendmodule\n')
            libs = [dict(model=str(model), declarations=g.library_declarations(model))]
            result = g.unique_models(libs, {'used'})
            self.assertEqual(g.declarations(result[str(model)]), ['used'])
        with self.assertRaises(ValueError):
            execute(Path('/nonexistent'), BaselineContext(), False, True, None, None)
        with self.assertRaises(ValueError):
            make_release(Path('/nonexistent'), BaselineContext(), False)
        with self.assertRaises(ValueError):
            reference(dict(path='relative', sha256='0' * 64))


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('action', choices=('prepare', 'check', 'release', 'check-release', 'execute', 'self-test'))
    parser.add_argument('--output', type=Path, default=DEFAULT)
    parser.add_argument('--release', type=Path)
    parser.add_argument('--release-sha256')
    parser.add_argument('--acknowledge-reconstruction', action='store_true')
    parser.add_argument('--authorize-compile', action='store_true')
    args = parser.parse_args()
    if args.action == 'self-test':
        require(not args.authorize_compile, 'Host tests never authorize EDA')
        return int(not unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(HostTests)).wasSuccessful())
    out = args.output.resolve()
    require(out == DEFAULT, 'Only owned baseline_01 output is supported')
    ctx = BaselineContext()
    if args.action == 'execute':
        return execute(out, ctx, args.authorize_compile, args.acknowledge_reconstruction,
                       args.release, args.release_sha256)
    require(not args.authorize_compile, 'Compile authorization only applies to execute')
    if args.action == 'prepare':
        receipt = prepare(out, ctx)
        print(json.dumps({k: receipt[k] for k in ('state', 'historical_byte_identity',
                                                'direct_sources', 'mapped_modules', 'external_cell_types')}))
    elif args.action == 'check':
        verify(read(out / 'source-pins.json'))
        print('HOST_PIN_CHECK_PASS (no EDA invoked)')
    elif args.action == 'release':
        print(json.dumps(make_release(out, ctx, args.acknowledge_reconstruction)))
    else:
        require(args.acknowledge_reconstruction, 'Reconstruction acknowledgement required')
        data = check_release(out, ctx, args.release, args.release_sha256)
        print(json.dumps(dict(state=data['state'], cases=[c['id'] for c in data['cases']], compile_authorized=False)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
