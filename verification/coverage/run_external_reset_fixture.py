"""One FPU-half EX2 fixture using the parent-owned shared UCLI reset driver."""
import argparse
from pathlib import Path
import re
import run_gap95_simulation as life
import run_gap115_axi_capture as focused
import run_external_tbpin_reset as fixture

OUT = life.OUT/'external-reset-fpu-half-ex2-old-image-745-agent-20261007-01'
DRIVER = Path(__file__).with_name('external_reset_driver.tcl').resolve()
DRIVER_TEST = Path(__file__).with_name('test_external_reset_driver.py').resolve()
PRE, PRE_SHA = fixture.PRE, fixture.PRE_SHA
require = fixture.require


def configuration(pre):
    t = fixture.target(pre)
    ara = 'ara_tb.dut.i_ara_soc.i_system.i_ara'
    return dict(ext_target=t['stage'], ext_value=6, ext_guard=t['valids'][1],
        ext_dump_objects=['ara_tb.clk', 'ara_tb.rst_n', ara+'.axi_req_o', ara+'.axi_resp_i',
                          t['stage'], *t['valids']])


def selection(c):
    require(set(c) == {'ext_target', 'ext_value', 'ext_guard', 'ext_dump_objects'} and c['ext_value'] == 6,
            'Exact FPU EX2 selection schema required')
    objects = c['ext_dump_objects']
    require(len(objects) == len(set(objects)) == 7 and c['ext_target'] in objects and c['ext_guard'] in objects
            and all(re.fullmatch(r'ara_tb(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[[0-9]+\])*)+', p)
                    for p in objects), 'Unsafe/duplicate focused object')
    return ('set ext_target {'+c['ext_target']+'}\nset ext_value 6\nset ext_guard {'+c['ext_guard']+
            '}\nset ext_dump_objects {'+' '.join(objects)+'}\n')


def command():
    name = 'vfpu_half_external_EX2_reset'
    return [str(life.IMAGE), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
        '+PRELOAD='+str(PRE/'input.elf'), '+TESTCASE='+name, '+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE='+str(OUT/'commit_trace.csv'), '+VECTOR_TRACE='+str(OUT/'vector_trace.csv'),
        '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(OUT/'code.vdb'), '-cm_name', name,
        '+ARA_UVM_TRACE_LIMIT=100000', '+ARA_CONTRACT_TRACE_LIMIT=100000',
        '-ucli', '-do', str(OUT.with_name(OUT.name+'.entry.tcl'))]


def prepare():
    require(not OUT.exists(), 'Fresh fixture output required')
    pre = life.read_bound(PRE/'preflight.json', PRE_SHA); c = configuration(pre)
    plan = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(plan['simv'] == str(life.IMAGE) and len(plan['image']) == 66, 'Frozen66 image required')
    pins = life.merge_pins(pre['pins'], plan['image'])
    pins = life.merge_pins(pins, {str(PRE/'preflight.json'): PRE_SHA, str(life.PLAN): life.PLAN_SEAL,
        str(focused.DOC): focused.DOC_SHA, str(focused.CONVERTER): focused.CONVERTER_SHA})
    for path in (DRIVER, DRIVER_TEST, Path(__file__).resolve(), Path(__file__).with_name('test_run_external_reset_fixture.py'),
                 Path(life.__file__).resolve(), Path(focused.__file__).resolve(), Path(fixture.__file__).resolve()):
        pins = life.merge_pins(pins, {str(path): life.digest(path)})
    life.check(pins)
    configpath = OUT.with_name(OUT.name+'.selection.tcl')
    with configpath.open('x') as f: f.write(selection(c))
    # life.run creates a fresh cwd. Copy the sealed selection there before sourcing the driver.
    entrypath = OUT.with_name(OUT.name+'.entry.tcl')
    with entrypath.open('x') as f:
        f.write('if {[file exists external-reset-selection.tcl]} {error "Existing reset selection"}\n'+
            'file copy {'+str(configpath)+'} external-reset-selection.tcl\nsource {'+str(DRIVER)+'}\n')
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in (configpath, entrypath)})
    record = dict(case='fpu_half_lane0_slot0_EX2', command=command(), pins=pins, timeout_s=600,
        selection=c, selection_source=str(configpath), selection_sha256=life.digest(configpath),
        preflight_seal=PRE_SHA, reset_pin='ara_tb.rst_n', reset_cycles=4,
        wave_byte_limit=64*1024*1024, no_automatic_AXI_reset=True, coverage_admitted=False,
        uvm_check_report_pass=False, parent_owned_shared_driver=True)
    path = OUT.with_name(OUT.name+'.prepared.json'); life.save(path, record)
    print(str(path)+' '+life.digest(path))


def run(seal):
    path = OUT.with_name(OUT.name+'.prepared.json'); record = life.read_bound(path, seal)
    require(record['command'] == command() and record['timeout_s'] == 600 and
            record['selection'] == configuration(life.read_bound(PRE/'preflight.json', PRE_SHA)),
            'Prepared fixture identity differs')
    record['pins'] = life.merge_pins(record['pins'], {str(path): seal})
    require(not OUT.exists(), 'No retry or overwrite')
    try:
        life.run(OUT, record)
        require(life.digest(OUT/'external-reset-selection.tcl') == record['selection_sha256'],
                'Executed cwd selection differs')
        wave = OUT/'external-reset.vpd'
        require(wave.is_file() and 0 < wave.stat().st_size <= record['wave_byte_limit'], 'Focused waveform limit')
        # Persist actual lines without interpreting echoed Tcl as executed markers. Full waveform/epoch qualification follows.
        text = (OUT/'console.log').read_text()
        lines = [line for line in text.splitlines() if line.startswith('EXT_RESET_')]
        life.save(OUT/'reset-capture.json', dict(status='FIXTURE_TERMINAL_PENDING_INDEPENDENT_RESET_AUDIT',
            markers=lines, wave_sha256=life.digest(wave), selection_sha256=record['selection_sha256'],
            coverage_admitted=False, uvm_check_report_pass=False))
    except Exception as exc:
        if OUT.exists(): life.save(OUT/'reset-capture-failure.json', dict(reason=str(exc), coverage_admitted=False))
        raise


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--prepare', action='store_true'); p.add_argument('--run-seal')
    a = p.parse_args(); require(bool(a.prepare) != bool(a.run_seal), 'Prepare or one sealed run')
    if a.prepare: prepare()
    else: run(a.run_seal)
