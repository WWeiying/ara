#!/usr/bin/env python3
"""Host-only GLS preparation for the exact 870cadb9 all-on DC attempt_03.

The compile argv in the plan requires an explicit authorized, frozen, directly service-owned compile
worker. Preparation and host checks never invoke EDA; no action runs GLS.
"""
import argparse
from collections import Counter
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import signal
import subprocess
import sys
import time
import unittest

ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
DEFAULT = OUT / 'power_gate_build_20261117_all_on_01'
RTL = OUT / 'power_rtl_20261117_host02'
DC = Path('/home/wangwy/dc_runs/ara_main_870cadb9_all_on_20261111_01/attempt_03')
DC_SOURCE = DC / 'sources/home/wangwy/openproject/ara_dsa_dc_20261110'
REV = '870cadb9f32c79df8d30ab845e4dd2e463a00540'
CHECKER_REV = 'dbe2b78817ef45b912444afcb85ad6e01a2be135'
V2_WORKER_SHA = '699bc377a22a0a6f98d976b48b511c053139df97e7377c55fbc18b3500e7646a'
UNIT = 'power-gate-build-20261117-all-on-01.service'
NET = DC / 'backend/syn/ara_soc/v1-dc/outputs/ara_soc_dc.v'
ANCHORS = {
    DC / 'source-pins.json': 'd9e6596f5e95e557a7955cabdb36d16d92de0cfb4a581ce3a77bbcf48afbd0e3',
    DC / 'manifest.json': '0a17d36c65573950c5e6dcd899cab65765e4183ef2b6443af9656426781e89d9',
    DC / 'status.json': '06513a3edbbcdd4c4878c87097b8ac4f022207b36ca02732b27ac05d2821d7b2',
    RTL / 'source-pins.json': '501826029b645db479065ffa7eb0cb55396dc5df40409e5628398902c6283fc5',
    RTL / 'rtl-receipt.json': 'a90251bb11be58e1c0e3d080a09a4c82a89b45b3a2dc36241d5cebb080f503aa',
}
DEFINES = {'SAIF', 'TARGET_GATESIM', 'TARGET_SRAM_MC', 'ARA_NO_FSDB',
           'POWER_CAPTURE_EXTERNAL',
           'NR_LANES=4', 'VLEN=1024', 'SIM_L2_SIZE_BYTES=1048576',
           'TARGET_CV64A6_IMAFDCV_SV39', 'ARIANE_ACCELERATOR_PORT=1',
           'ARA_QBS_ENABLE=1', 'ARA_AKV_ENABLE=1', 'ARA_AKV_V2_ENABLE=1',
           'ARA_QBS_LANE_MUL_ENABLE=1', 'ARA_SHARED_SIMD_MUL=1',
           'ARA_AKV_RESIDENT_PV_ENABLE=1', 'ARA_AKV_RESIDENT_QK_ENABLE=1',
           'COMMON_CELLS_ASSERTS_OFF', 'HPDCACHE_ASSERT_OFF', 'NO_SYNOPSYS_FF'}
TB = 'hardware/tb/ara_tb.sv'
HARNESS = 'hardware/tb/ara_testharness.sv'
UART = 'hardware/deps/cva6/corev_apu/tb/common/mock_uart.sv'


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


def save(path, obj):
    with Path(path).open('x') as stream:
        json.dump(obj, stream, indent=2, sort_keys=True)
        stream.write('\n')


def verify(pins):
    for name, expected in pins.items():
        require(sha(name) == expected, 'Identity drift: ' + str(name))


def uncomment(text):
    # Retain strings (including // in filenames) while removing SV comments.
    return re.sub(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/',
                  lambda m: m[0] if m[0].startswith('"') else ' ', text)


def declarations(text):
    return re.findall(r'\b(?:module|primitive|package)\s+(?:automatic\s+)?(\w+)', uncomment(text))


def library_declarations(path):
    names = []
    with path.open() as stream:
        for line in stream:
            match = re.match(r'^\s*(?:module|primitive)\s+(\w+)\b', line)
            if match:
                names.append(match[1])
    return names


def netlist_inventory(path):
    names, instances, banks, pending = [], set(), [], None
    module = re.compile(r'^[ \t]*module[ \t]+(\w+)')
    instance = re.compile(r'^  (\w+)[ \t]+(?:\\\S+|\w+)[ \t]*\(')
    bank = re.compile(r'^  TS1N28HPCPSVTB8192X128M4SWBASO[ \t]+(gen_dram_\d+__i_dram)[ \t]*\(')
    with path.open() as stream:
        for line in stream:
            m = module.match(line)
            if m:
                names.append(m[1])
            m = instance.match(line)
            if m:
                instances.add(m[1])
            elif pending and re.match(r'^[ \t]+(?:\\\S+|\w+)[ \t]*\(', line):
                instances.add(pending)
            m = bank.match(line)
            if m:
                banks.append(m[1])
            m = re.match(r'^  (\w+)[ \t]*$', line.rstrip('\n'))
            pending = m[1] if m else None
    return names, instances, banks


def unique_models(libraries, required):
    """Select original cell bodies; coalesce only identical shared definitions."""
    seen, prepared = {}, {}
    pattern = re.compile(r'^[ \t]*(module|primitive)\s+(\w+)\b[\s\S]*?'
                         r'^[ \t]*end(?:module|primitive)\b', re.M)
    for lib in libraries:
        text = Path(lib['model']).read_text()
        matches = list(pattern.finditer(text))
        require([m[2] for m in matches] == lib['declarations'], 'Unsupported model declaration layout')
        parts, previous, retained, removed = [], 0, [], []
        for match in matches:
            kind, name = match[1], match[2]
            body = match[0]
            parts.append(text[previous:match.start()])
            previous = match.end()
            reason = None
            if kind == 'module' and name not in required:
                reason = 'unused-cell'
            elif name in seen:
                canonical = lambda value: re.sub(r'\s+', '', uncomment(value))
                require(canonical(seen[name]) == canonical(body), 'Conflicting shared library definition: ' + name)
                reason = 'identical-shared-definition'
            else:
                seen[name] = body
                retained.append(name)
                parts.append(body)
            if reason:
                removed.append(dict(name=name, reason=reason))
        parts.append(text[previous:])
        lib['compiled_declarations'] = retained
        lib['removed_definitions'] = removed
        prepared[lib['model']] = ''.join(parts)
    return prepared


def project_tb(text, definitions):
    """Resolve conditional selectors only in the two known frozen TB files."""
    names = {d.split('=')[0] for d in definitions}
    active, stack, lines = True, [], []
    for line in text.splitlines():
        m = re.match(r'\s*`(ifdef|ifndef|elsif|else|endif)\b\s*(\w+)?', line)
        if m:
            op, name = m.groups()
            if op in ('ifdef', 'ifndef'):
                condition = (name in names) == (op == 'ifdef')
                stack.append([active, condition, False])
                active = active and condition
            else:
                require(stack, 'Unbalanced TB conditional')
                parent, seen, final = stack[-1]
                if op == 'endif':
                    active = stack.pop()[0]
                else:
                    require(not final, 'Conditional after else')
                    condition = op == 'else' or name in names
                    active = parent and not seen and condition
                    stack[-1] = [parent, seen or condition, op == 'else']
        elif active:
            m = re.match(r'\s*`(define|undef)\s+(\w+)', line)
            if m:
                if m[1] == 'define':
                    names.add(m[2])
                else:
                    names.discard(m[2])
            lines.append(line)
    require(not stack, 'Unterminated TB conditional')
    return '\n'.join(lines) + '\n'


def replace_once(text, before, after):
    require(text.count(before) == 1, 'Frozen TB anchor changed: ' + before[:70])
    return text.replace(before, after, 1)


def adapt_tb(text, banks):
    text = project_tb(text, DEFINES)
    start = text.index('  logic [63:0] wall_cycle;')
    end = text.index('  /*********\n   *  DUT', start)
    text = text[:start] + text[end:]
    start = text.index('  initial begin\n    string testcase;')
    end = text.index('  logic [63:0] exit;', start)
    text = (text[:start] + '  // TB-only successor guard; the frozen input is unchanged.\n'
            '`ifndef POWER_CAPTURE_EXTERNAL\n' + text[start:end] + '`endif\n' + text[end:])
    for bank, instance in enumerate(banks):
        old = f'dut.i_ara_soc.gen_dram[{bank} ].i_dram.preloadData(temp_file);'
        text = replace_once(text, old, f'dut.i_ara_soc.{instance}.preloadData(temp_file);')
    text, count = re.subn(
        r'(?m)^\s*\$display\("Cannot initialize address %x, which doesn\'t fall into the L2 region\.\", word_addr\);',
        '                $fatal(1, "ELF address %x outside exact 1 MiB gate memory", word_addr);', text)
    require(count == 1, 'Frozen SRAM bounds diagnostic changed')
    # Fail before any partially loaded row can cross the mapped SRAM boundary.
    text = replace_once(text, '        buffer = new[nwords * AxiWideBeWidth];',
        '        if (address < DRAMAddrBase || address >= DRAMAddrBase + L2SizeBytes ||\n'
        '            length > DRAMAddrBase + L2SizeBytes - address ||\n'
        '            address % AxiWideBeWidth != 0)\n'
        '          $fatal(1, "ELF section out of bounds or unaligned");\n'
        '        buffer = new[nwords * AxiWideBeWidth];')
    active = uncomment(project_tb(text, DEFINES))
    require('i_system' not in active and 'gen_dram[' not in active and '$dumpvars' not in active,
            'RTL hierarchy or uncontrolled VCD survived TB projection')
    return text


def adapt_harness(text):
    text = project_tb(text, DEFINES)
    text, count = re.subn(r'  ara_soc #\([\s\S]*?\n  \) i_ara_soc',
                          '  ara_soc i_ara_soc', text)
    require(count == 1 and 'i_system' not in uncomment(text), 'Gate harness derivation failed')
    return text


ROI = '''// External gate-only control; cycle one is the first rising edge after reset.
module power_capture;
  timeunit 1ns;
  timeprecision 100fs;
  longint unsigned cycles = 0, first_cycle, last_cycle, max_cycles;
  bit enabled = 0, done = 0;
  string filename;
  initial begin
    if (!$value$plusargs("GATE_MAX_CYCLES=%d", max_cycles) || max_cycles == 0)
      $fatal(1, "GATE_MAX_CYCLES is mandatory");
    if ($value$plusargs("GATE_VCD=%s", filename)) begin
      if (!$value$plusargs("GATE_ROI_FIRST=%d", first_cycle) ||
          !$value$plusargs("GATE_ROI_LAST=%d", last_cycle) ||
          first_cycle == 0 || last_cycle <= first_cycle || last_cycle >= max_cycles)
        $fatal(1, "Invalid mandatory bounded gate VCD window");
      enabled = 1;
    end
  end
  always @(posedge ara_tb.clk) begin
    if (ara_tb.rst_n) cycles <= cycles + 1;
    if (ara_tb.rst_n && cycles >= max_cycles) $fatal(1, "Gate watchdog");
    if (ara_tb.exit[0] && enabled && !done) $fatal(1, "Gate exit before ROI completion");
  end
  always @(negedge ara_tb.clk) begin
    if (enabled && ara_tb.rst_n && cycles == first_cycle) begin
      $display("GATE_ROI_BEGIN cycle=%0d time=%0t", cycles, $realtime);
      // Create the VCD here, including the complete initial state at this time.
      $dumpfile(filename);
      $dumpvars(0, ara_tb.dut.i_ara_soc);
    end
    if (enabled && ara_tb.rst_n && cycles == last_cycle) begin
      $dumpoff;
      $dumpflush;
      done = 1;
      $display("GATE_CAPTURE_WINDOW_COMPLETE cycle=%0d time=%0t task_pass=0", cycles, $realtime);
      if ($test$plusargs("GATE_STOP_AFTER_CAPTURE")) $finish;
    end
  end
endmodule
'''


def resolve_model(db):
    """Resolve one matching model family beneath this manifest library release."""
    if db.parent.name == 'DB':
        candidates = [db.parent.parent / 'VERILOG' / (db.stem + '.v')]
    else:
        # Family includes its threshold suffix before 'tt' in the actual name.
        family = re.sub(r'tt[0-9].*$', '', db.stem)
        release = next((p for p in db.parents if p.name.startswith('AN')), None)
        require(release is not None, 'No manifest library release: ' + str(db))
        candidates = list(release.glob('*_vlg/TSMCHOME/digital/Front_End/verilog/*/' + family + '.v'))
    candidates = [p for p in candidates if p.is_file()]
    require(len(candidates) == 1, 'Missing/ambiguous simulation model for ' + str(db))
    return candidates[0]


def package_closure(design, texts):
    packages = {}
    for path in design:
        for name in re.findall(r'\bpackage\s+(\w+)\s*;', uncomment(texts[path])):
            require(name not in packages, 'Duplicate package ' + name)
            packages[name] = path
    needed, pending = set(), ['ara_pkg']
    while pending:
        name = pending.pop()
        require(name in packages, 'Unknown package dependency: ' + name)
        path = packages[name]
        if path in needed:
            continue
        require(not re.search(r'\bmodule\s', uncomment(texts[path])), 'Mixed package/module input')
        needed.add(path)
        pending.extend(set(re.findall(r'\b(\w+)::', uncomment(texts[path]))) - {name})
    return [p for p in design if p in needed]


def prepare(out):
    require(not out.exists(), 'Fresh output required; no overwrite/retry')
    verify(ANCHORS)
    dc_pins, rtl_pins = read(DC / 'source-pins.json'), read(RTL / 'source-pins.json')
    verify(dc_pins)
    verify(rtl_pins)
    manifest, status, rtl = read(DC / 'manifest.json'), read(DC / 'status.json'), read(RTL / 'rtl-receipt.json')
    require(manifest['main_rtl_commit'] == REV and manifest['l2_mib'] == 1 and
            manifest['shared_fma'] and status['synthesis_flow_pass'] and
            rtl['revision'] == REV and rtl['dc_attempt'] == str(DC) and
            rtl['dc_source_bytes_changed'] == 0 and not rtl['fpga_gate_overlays_used'], 'Wrong DC/RTL contract')
    verify(status['output_sha256'])
    verify(manifest['library_sha256'])
    flist = DC / 'backend/flist/ara_soc_dc.f'
    require(sha(flist) == dc_pins[str(flist)], 'DC filelist drift')
    design = list(dict.fromkeys(Path(l.strip()) for l in flist.read_text().splitlines()
                               if l.strip().startswith('/')))
    require(all(str(p) in dc_pins and p.is_relative_to(DC_SOURCE) for p in design), 'Unpinned DC filelist source')
    texts = {p: p.read_text() for p in design}
    packages = package_closure(design, texts)
    net_names, instances, banks = netlist_inventory(NET)
    require(len(net_names) == len(set(net_names)) and net_names.count('ara_soc') == 1, 'Duplicate mapped modules')
    external = set(instances) - set(net_names)
    require(banks == [f'gen_dram_{i}__i_dram' for i in range(8)], 'Unexpected mapped DRAM instances')
    libraries = []
    for name, digest in manifest['library_sha256'].items():
        db = Path(name)
        if db.suffix == '.sldb':
            continue
        model = resolve_model(db)
        names = library_declarations(model)
        if set(names) & external:
            libraries.append(dict(db=str(db), db_sha256=digest, model=str(model),
                                  model_sha256=sha(model), declarations=names))
    model_text = unique_models(libraries, external)
    all_names = [*net_names, *(n for lib in libraries for n in lib['compiled_declarations'])]
    duplicates = [n for n, count in Counter(all_names).items() if count > 1]
    require(not duplicates, 'Duplicate mapped/library definitions: ' + repr(duplicates[:12]))
    require(not external - set(all_names), 'Unresolved mapped cells: ' + repr(sorted(external - set(all_names))[:20]))
    origins = dict(ANCHORS)
    origins.update(status['output_sha256'])
    origins.update(manifest['library_sha256'])
    out.mkdir()
    for directory in ('source', 'inputs', 'models', 'sim', 'logs', 'vcd'):
        (out / directory).mkdir()
    copied = {}

    def copy(src, dest, expected):
        verify({src: expected})
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        verify({dest: expected})
        origins[str(src)] = expected
        copied[str(dest.relative_to(out))] = dict(origin=str(src), sha256=expected)
        return dest

    paths = []
    for path in packages:
        rel = path.relative_to(DC_SOURCE)
        frozen = RTL / 'source' / rel
        require(rtl_pins[str(frozen)] == dc_pins[str(path)], 'Frozen package differs from DC')
        paths.append(copy(frozen, out / 'source' / rel, rtl_pins[str(frozen)]))
    # Copy only include headers from the frozen source inventory, never live deps.
    for name, digest in rtl_pins.items():
        p = Path(name)
        if p.is_relative_to(RTL / 'source') and p.suffix in ('.svh', '.vh'):
            copy(p, out / 'source' / p.relative_to(RTL / 'source'), digest)
    for rel in (TB, HARNESS, UART):
        p = RTL / 'source' / rel
        frozen = copy(p, out / 'inputs' / Path(rel).name, rtl_pins[str(p)])
        text = frozen.read_text()
        derived = adapt_tb(text, banks) if rel == TB else adapt_harness(text) if rel == HARNESS else text
        dest = out / 'source' / Path(rel).name
        dest.write_text(derived)
        paths.append(dest)
        if derived != text:
            (out / 'inputs' / (Path(rel).name + '.diff')).write_text(''.join(difflib.unified_diff(
                text.splitlines(True), derived.splitlines(True), fromfile=str(p), tofile=str(dest))))
    paths.append(copy(NET, out / 'source/ara_soc_dc.v', status['output_sha256'][str(NET)]))
    for lib in libraries:
        p = Path(lib['model'])
        copy(p, out / 'inputs/models' / p.name, lib['model_sha256'])
        dest = out / 'models' / p.name
        dest.write_text(model_text[str(p)])
        lib['compiled_model_sha256'] = sha(dest)
        require(declarations(model_text[str(p)]) == lib['compiled_declarations'], 'Filtered model declaration mismatch')
        lib['frozen_model'] = str(dest)
    dpi = copy(RTL / 'elfloader.o', out / 'elfloader.o', rtl_pins[str(RTL / 'elfloader.o')])
    worker = Path(__file__).resolve()
    copy(worker, out / 'inputs/build_gate.py', sha(worker))
    controller = out / 'source/power_capture.sv'
    controller.write_text(ROI)
    paths.append(controller)
    incdirs = []
    for line in flist.read_text().splitlines():
        if line.startswith('+incdir+'):
            for value in line[len('+incdir+'):].split('+'):
                dest = out / 'source' / Path(value).relative_to(DC_SOURCE)
                if dest.is_dir():
                    incdirs.append(dest)
    # Headers used by selected packages must resolve within the frozen closure.
    for p in paths:
        if p.name == 'ara_soc_dc.v':
            continue
        for inc in re.findall(r'`include\s+"([^"]+)"', uncomment(p.read_text())):
            require(any((d / inc).is_file() for d in [p.parent, *incdirs]), 'Unresolved frozen include: ' + inc)
    counts = Counter(n for p in paths for n in (net_names if p.name == 'ara_soc_dc.v' else declarations(p.read_text())))
    require(not any(v > 1 for v in counts.values()), 'Duplicate support/package definition')
    require(not set(counts) & {n for lib in libraries for n in lib['compiled_declarations']}, 'Support/library collision')
    lines = ['+define+' + d for d in sorted(DEFINES)]
    lines += ['+incdir+' + str(p) for p in dict.fromkeys(incdirs)]
    lines += [str(p) for p in paths]
    (out / 'sources.f').write_text('\n'.join(lines) + '\n')
    rtl_plan = read(RTL / 'plan.json')
    copy(RTL / 'plan.json', out / 'inputs/rtl-plan.json', rtl_pins[str(RTL / 'plan.json')])
    command = [rtl_plan['command'][0], '-full64', '-sverilog', '+v2k', '-debug_access+all',
               '+nospecify', '+notimingchecks', '-timescale=1ns/100fs',
               '-top', 'ara_tb', '-top', 'power_capture', '-f', str(out / 'sources.f'), str(dpi)]
    for lib in libraries:
        command.extend(['-v', lib['frozen_model']])
    command.extend(['-o', str(out / 'sim/simv'), '-l', str(out / 'logs/compile.vcs.log')])
    release_path = out / 'initial-release.json'
    save(release_path, initial_release())
    release_hash = sha(release_path)
    admission = check_release_data(read(reference(dict(path=str(release_path), sha256=release_hash))))
    save(out / 'initial-release-admission.json', dict(admission, release_sha256=release_hash))
    receipt = dict(schema='power-gate-static-v1', state='PREPARED_NOT_COMPILED',
        dc_attempt=str(DC), revision=REV, rtl_image=str(RTL), netlist_sha256=sha(NET),
        ddc_sha256=status['output_sha256'][str(NET.with_suffix('.ddc'))],
        memory=dict(bytes=1048576, bank_words=8192, bank_width=128, instances=banks,
                    preload_task='preloadData', hier_prefix='ara_tb.dut.i_ara_soc'),
        packages=[str(p.relative_to(DC_SOURCE)) for p in packages], libraries=libraries,
        direct_sources=len(paths), mapped_modules=len(net_names), external_cell_types=len(external),
        duplicate_definitions=[], unresolved_mapped_cell_types=[], copied_inputs=copied,
        adaptations=['Resolve SAIF/TARGET_GATESIM frozen TB conditionals',
            'Remove unguarded RTL-only lane history probes',
            'Remove parameter overrides on mapped ara_soc; retain harness parameters',
            'Use eight actual flattened netlist DRAM instance names',
            'Fail closed on out-of-bounds/unaligned ELF preload',
            'Guard original TB SAIF dumping with TB-only POWER_CAPTURE_EXTERNAL',
            'Dedicated power_capture starts dumpvars at selected start, not tail extraction',
            'Filter unused library modules and identical shared UDP/cell duplicates; retained bodies unchanged'],
        compile_authorized=False, eda_invoked=False, rtl_prechecks_verified=True,
        precheck_admission='TWO_INITIAL_CASES_ADMITTED_OTHER_CASES_UNKNOWN',
        admitted_cases=[c['id'] for c in admission['cases']], release_sha256=release_hash,
        timing_warning='ZERO-DELAY LOGIC GLS: +nospecify +notimingchecks, no SDF. '
            'Cell/SRAM behavioral procedural delays may remain. Not timing closure, '
            'glitch-accurate power, or signed-off 1 GHz operation.',
        limitations=['No direct RTL commit/vector/UVM/QBS_PERF monitors in mapped GLS.',
            'RTL numeric/protocol/path evidence must remain a separate matching precheck.',
            'Gate UART/tohost and bounded VCD are separate smoke/activity evidence, not RTL equivalence.',
            'GATE_CAPTURE_WINDOW_COMPLETE task_pass=0 is not full firmware completion or acceptance.',
            'ROI cycles are post-reset gate clock edges, not retired-instruction markers; '
            'validate actual gate window boundaries before reporting power.',
            'Library models resolved by manifest family/release, hashed separately from .db; '
            'Verilog model revisions can differ from timing database revisions.',
            'SRAM models warn against same-edge control changes; gate compile/smoke still required.',
            'DPI read_section byte/void declaration discrepancy inherited; return unused.'])
    save(out / 'gate-receipt.json', receipt)
    save(out / 'plan.json', dict(state='COMPILE_READY_FOR_TWO_ADMITTED_CASES_NOT_AUTHORIZED_OR_LAUNCHED',
        compile_argv_template_not_authorized=command, cwd=str(out / 'sim'),
        compilation_authorized=False, automatic_retry=False, environment_source=str(out / 'inputs/rtl-plan.json'),
        release=str(release_path), release_sha256=release_hash, compile_timeout_seconds=7200,
        prerequisites=['Explicit composite release checked by check-release for every selected ELF',
                       'Numerical PASS and independent protocol/image identities unchanged',
                       'Recovered protocol audits may join numeric PASS without relabeling failed original workers',
                       'Unresolved RTL/ABI failures block compile; offline protocol repair is not a simulator rerun',
                       'Explicit --authorize-compile on frozen worker directly owned by prepared systemd service'],
        stages=dict(zero_delay_smoke='No GATE_VCD; bounded watchdog; require checked UART/tohost completion',
                    complete_window='Exact prechecked ELF; GATE_VCD/FIRST/LAST and optional STOP_AFTER_CAPTURE; '
                                    'require GATE_ROI_BEGIN and GATE_CAPTURE_WINDOW_COMPLETE at exact cycles; '
                                    'window completion is activity only, not full-task PASS'),
        runtime=dict(required=['+PRELOAD=/absolute/checked.elf', '+GATE_MAX_CYCLES=N'],
            optional_vcd=['+GATE_VCD=/absolute/window.vcd', '+GATE_ROI_FIRST=N', '+GATE_ROI_LAST=M',
                          '+GATE_STOP_AFTER_CAPTURE'],
            clock_ns=1, selective_vcd=True, sdf=False, saif_conversion_run=False)))
    save(out / 'release-template.json', dict(schema='power-gate-release-v1', image=str(RTL),
        state='DRAFT_NOT_ADMITTED', cases=[dict(id='EXACT_CASE_ID',
            elf=dict(path='/absolute/prechecked.elf', sha256='EXACT_SHA256'),
            original_result=dict(path='/absolute/original/run/result.json', sha256='EXACT_SHA256'),
            numerical=dict(path='/absolute/original/run/numerical.json', sha256='EXACT_SHA256'),
            protocol=dict(path='/absolute/protocol.json', sha256='EXACT_SHA256'),
            protocol_audit=dict(path='/absolute/recovery/result.json', sha256='EXACT_SHA256'))],
        instructions='Set state=READY_FOR_AUDIT only after every selected case has evidence; '
            'omit protocol_audit only for original PASS. check-release also requires the release SHA256. '
            'Admission is limited to these exact ELF paths/hashes, not all manifest siblings; '
            'original aggregate need not pass and is never rewritten. No compile authorization.'))
    worker_command = ['/usr/bin/python3', '-B', str(out / 'inputs/build_gate.py'), 'execute',
        '--output', str(out), '--release', str(release_path), '--release-sha256', release_hash,
        '--authorize-compile']
    launcher = ['/usr/bin/systemd-run', '--user', '--unit=' + UNIT, '--property=Type=exec',
        '--property=KillMode=control-group', '--property=RuntimeMaxSec=7800',
        '--property=TimeoutStopSec=20', '--property=StandardOutput=append:' + str(out / 'service.stdout.log'),
        '--property=StandardError=append:' + str(out / 'service.stderr.log'), *worker_command]
    save(out / 'ready-command.json', dict(worker=worker_command, service=launcher,
        shell=shlex.join(launcher), vcs=command, launched=False, simulation_command=None))
    pins = {str(p): sha(p) for p in out.rglob('*') if p.is_file()}
    pins.update({str(p): h for p, h in origins.items()})
    save(out / 'source-pins.json', pins)
    verify(pins)
    save(out / 'status.json', dict(state='PREPARED_NOT_COMPILED', jobs_launched=0))
    return receipt


def reference(ref):
    require(isinstance(ref, dict) and set(ref) == {'path', 'sha256'}, 'Explicit path/hash reference required')
    path = Path(ref['path'])
    require(path.is_absolute() and path == path.resolve() and
            re.fullmatch(r'[0-9a-f]{64}', ref['sha256']), 'Invalid artifact reference')
    verify({path: ref['sha256']})
    return path


def protocol_gate(proof, c, row, work, image):
    runtime_image = {k: v for k, v in image.items() if k == str(RTL / 'sim/simv') or k.endswith('.so')}
    runtime_paths = {str(RTL / 'sim/simv')} | {str(p) for p in (RTL / 'sim/simv.daidir').rglob('*.so')}
    require(set(runtime_image) == runtime_paths, 'Uninventoried loader library')
    require(proof['status'] == 'PASS' and proof['issues'] == [] and
            proof['sim_image_sha256'] == runtime_image, 'Protocol PASS/runtime image inventory required')
    for field, expected in dict(elf_sha256=c['elf_sha256'], simv_sha256=image[str(RTL / 'sim/simv')],
            log_sha256=sha(work / 'run.vcs.log'), vector_trace_sha256=sha(work / 'vector.csv')).items():
        require(proof[field] == expected, 'Protocol identity mismatch: ' + field)
    counts = proof['contract_counts']
    require(all(counts[k] == 0 for k in ('exceptions', 'protocol_errors', 'outstanding')) and
            counts['requests'] == counts['responses'] > 0, 'Undrained/exceptional contract')
    for kind in ('uvm', 'backend'):
        count = proof[kind + '_counts']
        a, b = ('requests', 'responses') if kind == 'uvm' else ('allocations', 'completions')
        require(count[a] == count[b] > 0 and count['aborted'] == 0, 'Incomplete backend/protocol work')
    ar, aw = proof['axi_read_counts'], proof['axi_write_counts']
    require(ar['pending'] == aw['pending'] == ar['aborted'] == aw['aborted'] == 0 and
            ar['ar'] == ar['completed'] > 0 and aw['aw'] == aw['b'] == aw['matched'] > 0,
            'Incomplete AXI reads/writes')
    require(all(proof[k] > 0 for k in ('contract_event_count', 'uvm_event_count',
                'uvm_backend_event_count', 'vector_backend_event_count')), 'Missing independent trace events')


def check_release_data(release):
    require(release['schema'] == 'power-gate-release-v1' and release['state'] == 'READY_FOR_AUDIT'
            and release['image'] == str(RTL), 'Explicit matching composite release required')
    verify(ANCHORS)
    verify(read(RTL / 'source-pins.json'))
    build = read(RTL / 'build.json')
    image = read(RTL / 'image-pins.json')
    require(build['state'] == 'DC_MATCHED_RTL_BUILT_NOT_EXECUTED' and
            build['image_pins'] == image, 'Wrong RTL image build')
    verify(image)
    entries = release['cases']
    require(entries and len({e['id'] for e in entries}) == len(entries), 'Empty/duplicate release cases')
    admitted = []
    for entry in entries:
        require(re.fullmatch(r'[A-Za-z0-9_-]+', entry['id']), 'Invalid case ID')
        elf, original, numeric_path, protocol = [reference(entry[k]) for k in
                                               ('elf', 'original_result', 'numerical', 'protocol')]
        work = original.parent
        campaign = work.parent.parent
        require(campaign.parent == OUT and campaign.name.startswith('power_precheck_20261117_')
                and work.parent.name == 'runs' and work.name == entry['id'] and original.name == 'result.json'
                and numeric_path == work / 'numerical.json', 'Original evidence provenance mismatch')
        plan, row = read(campaign / 'plan.json'), read(original)
        candidates = [c for c in plan['cases'] if c['id'] == entry['id']]
        require(plan['image'] == str(RTL) and len(candidates) == 1, 'Precheck image/case mismatch')
        c = candidates[0]
        pins = read(campaign / 'source-pins.json')
        verify(pins)
        require(str(elf) == c['elf'] and entry['elf']['sha256'] == c['elf_sha256'] == row['elf_sha256']
                and row['id'] == entry['id'], 'Release ELF/case mismatch')
        if 'simulator_sha256' in row:
            require(row['simulator_sha256'] == image[str(RTL / 'sim/simv')], 'Legacy precheck image mismatch')
        else:
            v2_worker = campaign / 'inputs/precheck_v2.py'
            require(plan['protocol_checker_commit'] == CHECKER_REV and
                    plan['protocol_pythonpath'] == str(campaign / 'inputs/checker/verification') and
                    plan['accepted_image_states'] == ['DC_MATCHED_RTL_BUILT_NOT_EXECUTED',
                                                     'RECONSTRUCTED_BASELINE_RTL_BUILT_NOT_EXECUTED'] and
                    row['image_state'] == build['state'] and row['scope'] == plan['scope'] and
                    pins.get(str(v2_worker)) == V2_WORKER_SHA == sha(v2_worker), 'Unknown v2 row/checker configuration')
        numeric = read(numeric_path)
        require(numeric['state'] == 'PASS', 'Numerical PASS required, including successor ABI for Q8')
        require(pins.get(str(elf)) == c['elf_sha256'], 'ELF absent from precheck pins')
        if 'protocol_audit' in entry:
            audit_path = reference(entry['protocol_audit'])
            audit = read(audit_path)
            require(audit_path.parent.parent == OUT and audit_path.name == 'result.json', 'Wrong audit scope')
            audit_pins = read(audit_path.parent / 'source-pins.json')
            verify(audit_pins)
            require(row['state'] == 'FAIL' and row['error'] == "ValueError('PROTOCOL exit 1')" and
                    'ModuleNotFoundError: No module named' in (work / 'PROTOCOL.log').read_text(),
                    'Recovery is limited to the original missing-protocol-package failure')
            required_checks = {'returncode_zero', 'protocol_pass', 'no_issues', 'elf_identity',
                               'image_identity', 'log_identity', 'trace_identity', 'drained'}
            require(audit['state'] == 'PASS' and audit['original_worker_state'] == 'FAIL' and
                    audit['original_worker_reclassified'] is False and audit['rtl_rerun'] is False and
                    audit['numerical_evidence'] == str(numeric_path) and
                    audit['protocol_evidence'] == str(protocol) and
                    set(audit['checks']) == required_checks and all(v is True for v in audit['checks'].values()),
                    'Scoped protocol recovery receipt failed')
            for path in (original, numeric_path, work / 'PROTOCOL.log', work / 'run.vcs.log',
                         work / 'vector.csv', work / 'commit.csv'):
                require(audit_pins.get(str(path)) == sha(path), 'Audit lacks original evidence identity')
        else:
            require(row['state'] == 'PASS' and row['independent_protocol_checked'] and
                    row['numeric'] == numeric and protocol == work / 'protocol.json', 'Original checked PASS required')
        protocol_gate(read(protocol), c, row, work, image)
        admitted.append(dict(id=entry['id'], elf=str(elf), elf_sha256=c['elf_sha256'],
            original_worker_state=row['state'], original_worker_reclassified=False,
            numerical=entry['numerical'], protocol=entry['protocol'],
            protocol_audit=entry.get('protocol_audit'), original_result=entry['original_result']))
    return dict(state='COMPOSITE_RTL_EVIDENCE_ADMITTED_NOT_COMPILE_AUTHORIZATION',
                cases=admitted, original_aggregates_modified=False, compile_authorized=False)


def initial_release():
    entries = []
    selected = [('power_precheck_20261117_native_projection_01',
                 'qwen3_real_decode_attn_q_m1_n64_native', 'power_protocol_audit_20261117_q4_m1_01'),
                ('power_precheck_20261117_native_q8_successor_01', 'legacy_q8_qbs_sdk_v2_successor', None)]
    for campaign, case_id, recovery in selected:
        directory = OUT / campaign
        c = next(c for c in read(directory / 'plan.json')['cases'] if c['id'] == case_id)
        work = directory / 'runs' / case_id
        ref = lambda p: dict(path=str(p), sha256=sha(p))
        entry = dict(id=case_id, elf=ref(Path(c['elf'])), original_result=ref(work / 'result.json'),
                     numerical=ref(work / 'numerical.json'),
                     protocol=ref((OUT / recovery if recovery else work) / 'protocol.json'))
        if recovery:
            entry['protocol_audit'] = ref(OUT / recovery / 'result.json')
        entries.append(entry)
    return dict(schema='power-gate-release-v1', state='READY_FOR_AUDIT', image=str(RTL), cases=entries)


def execute(out, authorized, release, release_hash):
    require(authorized, 'Explicit --authorize-compile is mandatory')
    require(Path(__file__).resolve() == out / 'inputs/build_gate.py', 'Use frozen worker only')
    require(not (out / 'attempt.json').exists(), 'No automatic retry; preserve failed output')
    plan = read(out / 'plan.json')
    require(release is not None and str(release) == plan['release'] and release_hash == plan['release_sha256'],
            'Compile release must match the prepared admission')
    verify(read(out / 'source-pins.json'))
    reference(dict(path=str(release), sha256=release_hash))
    admission = check_release_data(read(release))
    group = Path('/proc/self/cgroup').read_text()
    owner = subprocess.check_output(['/usr/bin/systemctl', '--user', 'show', UNIT,
                                     '-p', 'MainPID', '--value'], text=True).strip()
    require('/' + UNIT in group and owner == str(os.getpid()), 'Direct systemd service ownership required')
    save(out / 'attempt.json', dict(pid=os.getpid(), cgroup=group, started=time.time(),
                                   release_sha256=release_hash, admission=admission))
    report = dict(state='FAIL', gls_runs=0, timing_acceptance=False, power_acceptance=False)
    proc = None
    try:
        command = plan['compile_argv_template_not_authorized']
        require('-R' not in command and '+nospecify' in command and '+notimingchecks' in command,
                'Unexpected compile/simulation options')
        with (out / 'compile.console.log').open('x') as stream:
            proc = subprocess.Popen(command, cwd=plan['cwd'],
                env=read(plan['environment_source'])['environment'], stdout=stream, stderr=subprocess.STDOUT,
                start_new_session=True)
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
        image = {str(p): sha(p) for p in (out / 'sim/simv.daidir').rglob('*') if p.is_file()}
        image[str(out / 'sim/simv')] = sha(out / 'sim/simv')
        save(out / 'image-pins.json', image)
        report.update(state='DC_MATCHED_GATE_BUILT_NOT_SIMULATED', image_pins=image,
                      admitted_cases=[c['id'] for c in admission['cases']], release_sha256=release_hash)
    except Exception as exc:
        report['error'] = repr(exc)
    save(out / 'build.json', report)
    save(out / 'compile-status.json', dict(state=report['state'], finished=time.time()))
    print(json.dumps(report))
    return int(report['state'] == 'FAIL')


class HostTests(unittest.TestCase):
    def test_projection(self):
        text = '`ifdef SAIF\na\n`ifndef TARGET_GATESIM\nb\n`else\nc\n`endif\n`else\nd\n`endif\n'
        self.assertEqual(project_tb(text, DEFINES), 'a\nc\n')
        with self.assertRaises(ValueError):
            project_tb('`else\n', set())
        with self.assertRaises(ValueError):
            project_tb('`ifdef X\n', set())

    def test_closure_and_comments(self):
        a, b = Path('/a'), Path('/b')
        texts = {a: 'package dep; endpackage', b: 'package ara_pkg; dep::x t; endpackage'}
        self.assertEqual(package_closure([a, b], texts), [a, b])
        self.assertEqual(declarations('// module bad\nmodule good (); /* module bad */ endmodule'), ['good'])
        self.assertEqual(declarations('module long_name\n (x);'), ['long_name'])
        self.assertEqual(re.sub(r'tt[0-9].*$', '', 'familyhvttt0p9v25c'), 'familyhvt')
        with self.assertRaises(ValueError):
            reference(dict(path='relative', sha256='0' * 64))
        with self.assertRaises(ValueError):
            check_release_data(dict(schema='power-gate-release-v1', state='DRAFT', image=str(RTL)))

    def test_library_duplicates(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory(prefix='power-gate-host-test-') as directory:
            a, b = Path(directory) / 'a.v', Path(directory) / 'b.v'
            a.write_text('module cell_a ();\nendmodule\nprimitive shared ();\nendprimitive\n')
            b.write_text('module unused ();\nendmodule\nprimitive shared ();\nendprimitive\n')
            libs = [dict(model=str(p), declarations=library_declarations(p)) for p in (a, b)]
            result = unique_models(libs, {'cell_a'})
            self.assertEqual(declarations(result[str(a)]), ['cell_a', 'shared'])
            self.assertEqual(declarations(result[str(b)]), [])
            b.write_text('primitive shared (different);\nendprimitive\n')
            libs[1]['declarations'] = library_declarations(b)
            with self.assertRaises(ValueError):
                unique_models(libs, {'cell_a'})

    def test_frozen_adapters(self):
        tb = adapt_tb((RTL / 'source' / TB).read_text(), [f'gen_dram_{i}__i_dram' for i in range(8)])
        harness = adapt_harness((RTL / 'source' / HARNESS).read_text())
        self.assertEqual(uncomment(tb).count('.preloadData(temp_file)'), 8)
        self.assertNotIn('i_system', uncomment(tb + harness))
        self.assertIn('`ifndef POWER_CAPTURE_EXTERNAL', tb)
        self.assertNotIn('$dumpvars', project_tb(tb, DEFINES))
        self.assertEqual(ROI.count('$dumpvars'), 1)
        self.assertIn('module power_capture;', ROI)
        self.assertIn('task_pass=0', ROI)
        self.assertNotIn('ara_soc #(', harness)
        self.assertIn('GATE_MAX_CYCLES', ROI)
        with self.assertRaises(ValueError):
            execute(Path('/nonexistent'), False, None, None)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('action', choices=('prepare', 'check', 'check-release', 'execute', 'self-test'))
    parser.add_argument('--output', type=Path, default=DEFAULT)
    parser.add_argument('--release', type=Path)
    parser.add_argument('--release-sha256')
    parser.add_argument('--authorize-compile', action='store_true')
    args = parser.parse_args()
    if args.action == 'self-test':
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(HostTests)
        return int(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
    out = args.output.resolve()
    require(out == DEFAULT, 'Only the owned all_on_01 output is supported')
    if args.action == 'execute':
        return execute(out, args.authorize_compile, args.release, args.release_sha256)
    require(not args.authorize_compile, 'Compile authorization only applies to execute')
    if args.action == 'prepare':
        receipt = prepare(out)
        print(json.dumps({k: receipt[k] for k in ('state', 'direct_sources', 'mapped_modules', 'external_cell_types')}))
    elif args.action == 'check':
        verify(read(out / 'source-pins.json'))
        print('HOST_PIN_CHECK_PASS (no EDA invoked)')
    else:
        require(args.release is not None and args.release_sha256, '--release and --release-sha256 are required')
        path = reference(dict(path=str(args.release), sha256=args.release_sha256))
        require(path.is_relative_to(OUT), 'Release must be preserved OUT evidence')
        report = check_release_data(read(path))
        verify({path: args.release_sha256})
        print(json.dumps(dict(report, release=str(path), release_sha256=args.release_sha256)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
