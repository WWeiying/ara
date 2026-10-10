"""Exact three-group FSM capture/application; no other waiver families."""
import argparse
import csv
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from closure_point_inventory import read_xml
import run_admitted_741_dve as report
import dve_tool_identity as tool

life, require = report.life, report.require
HERE = Path(__file__).resolve().parent
HOOK = HERE / 'fsm741_transition_native.tcl'
BUILD = life.OUT / 'repaired-aligned-build-20260930-01'
PORT = 'ara_tb.dut.i_ara_soc.i_system.i_ariane.gen_cache_wt.i_cache_subsystem.i_wt_dcache.gen_rd_ports[2].genblk1.i_wt_dcache_ctrl'
DISPATCH = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher'
PTW = 'ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.lsu_i.gen_mmu.i_cva6_mmu.i_ptw'
SOURCES = {
    PORT: ('hardware/deps/cva6/core/cache_subsystem/wt_dcache_ctrl.sv', '3476102610', 28),
    DISPATCH: ('hardware/src/ara_dispatcher.sv', '1099616778', 92),
    PTW: ('hardware/deps/cva6/core/cva6_mmu/cva6_ptw.sv', '3345966803', 35),
}
for lane in range(4):
    prefix = 'ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d].i_lane.i_vfus.' % lane
    SOURCES[prefix + 'i_vmfpu'] = ('hardware/src/lane/vmfpu.sv', '3873291691', 37)
for lane in range(4):
    prefix = 'ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d].i_lane.i_vfus.' % lane
    SOURCES[prefix + 'i_valu'] = ('hardware/src/lane/valu.sv', '1674936110', 21)


def candidate(scope, machine, mode, source, dest):
    if mode == 'State':
        return False
    if scope == PORT:
        return mode == 'Transition' or dest != 'IDLE'
    if scope == PTW:
        return 'PROPAGATE_ACCESS_ERROR' in (source, dest)
    if scope not in (PORT, DISPATCH, PTW):
        lane = int(scope.split('gen_lanes[')[1].split(']')[0])
        forbidden = 'LN0_REDUCTION_COMMIT' if lane == 0 else 'SIMD_REDUCTION'
        require(machine == ('mfpu_state_q' if scope.endswith('.i_vmfpu') else 'alu_state_q'), 'Unexpected lane FSM')
        return forbidden in (source, dest)
    return (machine == 'state_q' and mode == 'Transition' and dest == 'WAIT_STORE_RESPONSE'
            and source not in {'NORMAL_OPERATION', 'OVERLAP_ISSUE_ORIGINAL', 'WAIT_IDLE', 'WAIT_IDLE_FLUSH'})


def groups_from_shape(shape, bitmap):
    groups = []
    for scope, (relative, checksum, width) in SOURCES.items():
        record = bitmap['metrics']['fsm'][scope]
        require(record['checksum'] == checksum and record['width'] == width, 'Metric identity differs')
        nodes = [n for n in shape.iter('fsmdef') if n.get('chksum') == checksum and
                 any(i.get('name') == scope for i in n.findall('fsminst'))]
        require(len(nodes) == 1, 'FSM compiled instance ambiguous')
        offset = 0
        for machine in nodes[0].iter('fsmfsm'):
            states = machine.findall('state')
            by_id = {s.get('id'): s for s in states}
            for mode, items in [('State', states), ('Transition', machine.findall('transition'))]:
                rows = []
                for item in items:
                    source = by_id[item.get('fromid')].get('name') if mode == 'Transition' else None
                    dest = by_id[item.get('toid')].get('name') if mode == 'Transition' else item.get('name')
                    name = source + '->' + dest if source else dest
                    target = candidate(scope, machine.get('name'), mode, source, dest)
                    hit = bool(int(record['bits'], 16) & (1 << (width - 1 - offset)))
                    require(not target or not hit, 'Observed hit contradicts source proof')
                    rows.append(dict(name=name, raw_index=offset, target=target,
                                     attributes=dict(item.attrib), source=source, destination=dest))
                    offset += 1
                require(len({r['name'] for r in rows}) == len(rows), 'Duplicate compiled selector')
                groups.append(dict(scope=scope, source=relative, checksum=checksum,
                                   machine=dict(machine.attrib), mode=mode, rows=rows))
        require(offset == width, 'FSM width differs')
    require([sum(r['target'] for g in groups if g['scope'] == s for r in g['rows'])
             for s in SOURCES] == [20, 11, 3] + [5] * 4 + [3] * 4, 'Exact group targets differ')
    require(sum(len(g['rows']) for g in groups) == 387, 'Full protected inventory differs')
    return groups


def tcl_atom(value):
    require(not any(c in value for c in '{}\\\n\r'), 'Unsafe Tcl atom')
    return '{' + value + '}'


def run(out, full):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh output required')
    raw = life.read_bound(report.admission.RAW, report.admission.RAW_SHA)
    book = life.read_bound(report.BASE / 'admission-manifest.json', report.SEAL)
    pins = life.merge_pins(book['input_pins'], book['output_pins'])
    pins = life.merge_pins(pins, {str(report.BASE / 'admission-manifest.json'): report.SEAL,
                                str(report.admission.RAW): report.admission.RAW_SHA})
    bits = life.read_bound(report.BASE / 'combined-bits.json', pins[str(report.BASE / 'combined-bits.json')])
    require(len(bits['tests']) == len(set(bits['tests'])) == 741, 'Not exact741 population')
    design = Path(raw['input_ledger'][0])
    shape_path = design / 'snps/coverage/db/shape/fsm.verilog.shape.xml'
    require(pins[str(shape_path)] == bits['design']['shape/fsm.verilog.shape.xml'], 'Design shape differs')
    build_path = BUILD / 'build-source-pins.json'
    build_sha = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
    build = life.read_bound(build_path, build_sha)
    pins = life.merge_pins(pins, {str(build_path): build_sha})
    groups = groups_from_shape(read_xml(shape_path), bits)
    for scope, (relative, _, _) in SOURCES.items():
        source = life.ROOT / relative if scope != DISPATCH else life.ROOT.parent / 'ara_dsa' / relative
        pins = life.merge_pins(pins, {str(source): build[str(life.ROOT / relative)]})
    # Bind the complete accepted port2 producer chain and PMP0 configuration sources.
    for relative in ('hardware/src/ara.sv', 'hardware/src/lane/lane.sv', 'hardware/src/lane/vector_fus_stage.sv', 'hardware/deps/cva6/core/cva6.sv', 'hardware/deps/cva6/core/acc_dispatcher.sv',
                     'hardware/deps/cva6/core/cache_subsystem/wt_dcache.sv', 'hardware/src/ara_soc.sv',
                     'hardware/deps/cva6/core/include/build_config_pkg.sv',
                     'hardware/deps/cva6/core/pmp/src/pmp.sv'):
        p = life.ROOT / relative
        pins = life.merge_pins(pins, {str(p): build[str(p)]})
    dependencies = [Path(__file__).resolve(), HOOK, HERE / 'test_fsm741_transition_native.py', HERE / 'fsm741_transition_batch.py', HERE / 'test_fsm741_transition_batch.py', HERE / 'fsm741_transition_batch.tcl', HERE / 'fsm741_transition_capture.py', HERE / 'test_fsm741_transition_capture.py', HERE / 'fsm741_exact_capture.py', HERE / 'test_fsm741_exact_capture.py',
                    HERE / 'fsm741_native_singleton.tcl', HERE / 'fsm741_native_probe.tcl',
                    HERE / 'discover_ptw_pmp0_fsm_v2.tcl', HERE / 'apply_points740_v4.tcl',
                    HERE / 'export_dve_coverage.tcl', Path(tool.__file__).resolve()]
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in dependencies})
    life.check(pins)
    tool.revalidate(raw['tool_identity'])
    ledger = (report.BASE / 'combined-inputs.txt').read_text().splitlines()
    require(ledger == raw['input_ledger'] + [str(report.admission.VDB)] and len(set(ledger)) == 742,
            '741 exact input prefix differs')
    if not full:
        ledger = ledger[:2]
    selected = []
    for vdb in ledger:
        testroot = Path(vdb) / 'snps/coverage/db/testdata'
        if testroot.is_dir():
            for test in sorted(testroot.iterdir()):
                if test.is_dir():
                    selected.append(str(Path(vdb).with_suffix('') / test.name))
    require(len(selected) == len(set(selected)) == (741 if full else 1), 'Selected test identity differs')
    out.mkdir()
    life.save(out / 'plan.json', dict(groups=groups, pins=pins, selected=selected, input_ledger=ledger,
                                    targets=66, protected=321, population=741 if full else 1,
                                    historical741_seal=report.SEAL, no_other_waivers=True, strategy='direct-transition-only-66', state_display_inheritance_observed=True, point_query_authority='saved-native-identity'))
    with (out / 'inputs.txt').open('x') as f:
        f.write('\n'.join(ledger) + '\n')
    with (out / 'selection.tcl').open('x') as f:
        f.write('set fx_groups {}\n')
        for group in groups:
            source = life.ROOT / group['source'] if group['scope'] != DISPATCH else life.ROOT.parent / 'ara_dsa' / group['source']
            names = ' '.join(tcl_atom(r['name']) for r in group['rows'])
            targets = ' '.join(tcl_atom(r['name']) for r in group['rows'] if r['target'])
            values = [group['scope'], str(source), group['machine']['name'], group['mode']]
            f.write('lappend fx_groups [list ' + ' '.join(tcl_atom(v) for v in values) +
                    ' [list ' + names + '] [list ' + targets + ']]\n')
    pins = life.merge_pins(pins, {str(out / n): life.digest(out / n) for n in ('plan.json', 'inputs.txt', 'selection.tcl')})
    env = tool.controlled_environment(raw['tool_identity'], os.environ)
    env.pop('DVE', None)
    env.update(DVE_COVERAGE_OUTPUT=str(out), DVE_REVIEWED_WAIVERS=str(HOOK), FSM_PROBE_OUTPUT=str(out))
    process = None
    result = dict(status='RUNNING', population=741 if full else 1)
    try:
        with (out / 'launcher.log').open('x') as stream:
            process = subprocess.Popen(tool.launch_command(raw['tool_identity'], HERE / 'export_dve_coverage.tcl'),
                                       cwd=out, env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            start = tool.process_info(process.pid)['starttime']
            deadline = time.monotonic() + 60
            live = None
            while process.poll() is None and time.monotonic() < deadline:
                for p in Path('/proc').iterdir():
                    if not p.name.isdigit():
                        continue
                    try:
                        if (p / 'exe').resolve() == Path(raw['tool_identity']['executable']):
                            live = tool.verify_live_executable(int(p.name), raw['tool_identity'], process.pid, start)
                            break
                    except (OSError, ValueError):
                        pass
                if live:
                    break
                time.sleep(.2)
            require(live is not None, 'No launch-bound DVE')
            life.save(out / 'live-identity.json', live)
            (out / 'live-ready').touch()
            print('FSM741_EXACT_LIVE pid=%s launch=%s' % (live['pid'], process.pid), flush=True)
            code = process.wait(timeout=900 if full else 300)
        life.check(pins)
        tool.revalidate(raw['tool_identity'])
        log = (out / 'DVEfiles/dve_gui.log').read_text()
        require(code == 0 and log.splitlines().count('FSM741_EXACT_DONE') == 1 and
                'FSM741_EXACT_FAILED' not in log and 'DVE_COVERAGE_EXPORT_FAILED' not in log,
                'Exact session failed; preserve native evidence')
        require((out / 'selected_tests.txt').read_text().splitlines() == selected, 'Native selected tests differ')
        require(all((out / n).read_bytes() == b'' for n in ('initial.el', 'reset.el', 'final-empty.el', 'cleanup-empty.el')),
                'Global reset not empty')
        require((out / 'first.el').read_bytes() == (out / 'second.el').read_bytes() != b'', 'EL serialization differs')
        audit = list(csv.reader((out / 'exact-audit.tsv').open(), delimiter='\t'))
        require(len(audit) == 5 * 387 and all((r[0] in ('applied', 'reloaded') and r[-1] in ('INHERITED_OBSERVATION', 'NATIVE_EL_AUTHORITY') and r[-2] in ('0', '1')) or r[-2] == r[-1] for r in audit), 'Incomplete protected audit')
        result.update(status='EXACT66_CAPTURE_REQUIRES_NATIVE_SIGNATURE_REVIEW', targets=42, protected=113,
                      first_sha256=life.digest(out / 'first.el'), returncode=code)
    except Exception as exc:
        result.update(status='FAILED', reason=str(exc))
        raise
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        life.save(out / 'status.json', result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--full741', action='store_true')
    args = parser.parse_args()
    run(args.output.absolute(), args.full741)
