"""One FPU-half EX2 representative using shared external-TB-reset UCLI; no admission."""
import argparse
from pathlib import Path
import re
import run_gap95_simulation as life
import run_gap115_axi_capture as focused

TCL = Path(__file__).with_name('external_tbpin_reset.tcl').resolve()
PRE = life.OUT/'fpu-half-active-reset-preflight744-agent-20261007-01'
PRE_SHA = 'be3a04f26588e1a355f3a73f96ff7043fb306daf7d4555cfb5887439b7d47cbf'
OUT = life.OUT/'external-tbpin-fpu-half-ex2-old-image-745-agent-20261007-01'
ROUTE = 'fpu_half_lane0_slot0_EX2'


def require(ok, message):
    if not ok: raise ValueError(message)


def target(pre):
    require(pre['status'] == 'HOST_SPIKE679_PASS_RESET_TIMING_MEASUREMENT_PENDING' and
            pre['coverage_admitted'] is False and len(pre['targets']) == 16, 'Frozen FPU preflight differs')
    selected = [r for r in pre['targets'] if '.gen_lanes[0].' in r['scope'] and '.gen_num_lanes[0].' in r['scope']]
    require(len(selected) == 1 and selected[0]['primary_raw_index'] == 8, 'Exact lane0/slot0 controller required')
    scope = selected[0]['scope']
    return dict(route=ROUTE, stage=scope+'.div_cur_state', code=6,
                valids=[scope+'.vfdsu_dp_fdiv_busy', scope+'.vfdsu_ex2_half'])


def entry(t):
    paths = [t['stage'], *t['valids']]
    require(t['route'] == ROUTE and t['code'] == 6 and len(set(paths)) == 3 and
            all(re.fullmatch(r'ara_tb(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[[0-9]+\])*)+', p) for p in paths),
            'Unsafe target configuration')
    return ('source {'+str(TCL)+'}\nif {[catch {\n    etbr_execute '+ROUTE+' {'+t['stage']+'} 6 {'+
            ' '.join(t['valids'])+'}\n} message]} {\n    puts stderr "ETBR_ERROR $message"\n    exit 1\n}\n')


def command():
    name = 'vfpu_half_external_EX2_reset'
    return [str(life.IMAGE), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
        '+PRELOAD='+str(PRE/'input.elf'), '+TESTCASE='+name, '+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE='+str(OUT/'commit_trace.csv'), '+VECTOR_TRACE='+str(OUT/'vector_trace.csv'),
        '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(OUT/'code.vdb'), '-cm_name', name,
        '+ARA_UVM_TRACE_LIMIT=100000', '+ARA_CONTRACT_TRACE_LIMIT=100000',
        '-ucli', '-do', str(OUT.with_name(OUT.name+'.entry.tcl'))]


def prepare():
    require(not OUT.exists(), 'Fresh run output required')
    pre = life.read_bound(PRE/'preflight.json', PRE_SHA); t = target(pre)
    plan = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(plan['simv'] == str(life.IMAGE) and len(plan['image']) == 66, 'Frozen66 image required')
    pins = life.merge_pins(pre['pins'], plan['image'])
    pins = life.merge_pins(pins, {str(PRE/'preflight.json'): PRE_SHA, str(life.PLAN): life.PLAN_SEAL,
                                str(focused.DOC): focused.DOC_SHA, str(focused.CONVERTER): focused.CONVERTER_SHA})
    book = life.OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    sources = life.read_bound(book, '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b')
    ctrl = life.ROOT/'hardware/deps/fpnew/vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl/ct_vfdsu_ctrl.v'
    pins = life.merge_pins(pins, {str(ctrl): sources[str(ctrl)]})
    for p in (TCL, Path(__file__).resolve(), Path(__file__).with_name('test_external_tbpin_reset.py'),
              Path(life.__file__).resolve(), Path(focused.__file__).resolve()):
        pins = life.merge_pins(pins, {str(p): life.digest(p)})
    life.check(pins)
    text = ctrl.read_text()
    require("parameter EX2       = 4'b0110;" in text and
            'assign div_st_ex2' in text and 'vfdsu_ex2_half' in text, 'Frozen EX2/format semantics differ')
    script = OUT.with_name(OUT.name+'.entry.tcl')
    with script.open('x') as f: f.write(entry(t))
    pins = life.merge_pins(pins, {str(script): life.digest(script)})
    record = dict(case=ROUTE, command=command(), pins=pins, timeout_s=600, target=t,
        preflight_seal=PRE_SHA, no_automatic_AXI_reset=True, reset_drive_pin='ara_tb.rst_n',
        reset_negedges=4, wave_byte_limit=64*1024*1024, coverage_admitted=False, uvm_check_report_pass=False)
    path = OUT.with_name(OUT.name+'.prepared.json'); life.save(path, record)
    print(str(path)+' '+life.digest(path))


def markers(text, t):
    lines = text.splitlines()
    require(not any(re.match(r'^(ETBR_ERROR|Error-|UCLI_ERROR)', line) for line in lines), 'Actual UCLI error')
    stage = t['stage']; route = t['route']
    expected = ['ETBR_ARMED %s %s %d'%(route, stage, t['code'])]
    expected += ['ETBR_VALID '+p+' 1' for p in t['valids']]
    expected += ['ETBR_TARGET %s %s %d'%(route, stage, t['code']), 'ETBR_ASSERT '+route+' 0']
    expected += ['ETBR_LOW_EDGE %s %d'%(route, i) for i in range(1, 5)]
    expected += ['ETBR_RELEASE '+route+' 1', 'ETBR_RECOVERY '+route]
    actual = [line for line in lines if line.startswith('ETBR_') and not line.startswith('ETBR_OBJECT ')]
    require(actual == expected, 'Exact executed reset phases differ; echo is not evidence')
    ara = 'ara_tb.dut.i_ara_soc.i_system.i_ara'
    objects = ['ara_tb.clk', 'ara_tb.rst_n', ara+'.axi_req_o', ara+'.axi_resp_i', stage, *t['valids']]
    require([line for line in lines if line.startswith('ETBR_OBJECT ')] == ['ETBR_OBJECT '+p for p in objects],
            'Focused object inventory differs')
    return dict(status='EXACT_EXTERNAL_TBPIN_RESET_MARKERS_NOT_ARCHITECTURE_QUALIFICATION',
                target=t, reset_negedges=4, uvm_check_report_pass=False, coverage_admitted=False)


def run(seal):
    path = OUT.with_name(OUT.name+'.prepared.json'); record = life.read_bound(path, seal)
    pre = life.read_bound(PRE/'preflight.json', PRE_SHA)
    require(record['command'] == command() and record['target'] == target(pre) and record['timeout_s'] == 600,
            'Prepared command/target differs')
    record['pins'] = life.merge_pins(record['pins'], {str(path): seal})
    require(not OUT.exists(), 'No retry/overwrite')
    try:
        life.run(OUT, record)
        result = markers((OUT/'console.log').read_text(), record['target'])
        wave = OUT/'focused-reset.vpd'
        require(wave.is_file() and 0 < wave.stat().st_size <= record['wave_byte_limit'], 'Focused waveform limit')
        result['wave_sha256'] = life.digest(wave); life.save(OUT/'reset-observation.json', result)
    except Exception as exc:
        if OUT.exists(): life.save(OUT/'reset-observation-failure.json', dict(reason=str(exc), coverage_admitted=False))
        raise


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--prepare', action='store_true'); p.add_argument('--run-seal')
    a = p.parse_args(); require(bool(a.prepare) != bool(a.run_seal), 'Prepare or one sealed run')
    if a.prepare: prepare()
    else: run(a.run_seal)
