"""One authorized slot15 AUX cancellation measurement on the frozen image/ELF."""
import argparse
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace

import run_qbs_affine_external_reset as old

life, require = old.life, old.require
BASE = life.OUT/'qbs-affine-min-scale-offline-admitted-760-agent-20261007-01'
BASE_SHA = '0b4ae9ddf332355cdbb02ff42f237487dd0857fa5872b86916bc5ac40b3b207e'
SCOPE, PRE, PRE_SHA = old.SCOPE, old.PRE, old.PRE_SHA
STAGES = {'aux': (1, 279)}
focused = old.focused
HERE = Path(__file__).resolve().parent


def configuration(stage):
    require(stage == 'aux', 'Only slot15 AUX authorized')
    result = old.configuration(stage)
    result['ext_target'] = SCOPE+'.entry_state_q[15]'
    result['ext_guard'] = SCOPE+'.entry_valid_q[15]'
    result['ext_dump_objects'] = ['ara_tb.clk', 'ara_tb.rst_n',
        'ara_tb.dut.i_ara_soc.i_system.i_ara.axi_req_o',
        'ara_tb.dut.i_ara_soc.i_system.i_ara.axi_resp_i',
        SCOPE+'.entry_valid_q', SCOPE+'.entry_inflight_q',
        *[SCOPE+'.entry_state_q[%d]' % slot for slot in range(16)]]
    return result


def selection(stage):
    c = configuration(stage)
    return ('set ext_target {'+c['ext_target']+'}\nset ext_value 1\nset ext_guard {'+
            c['ext_guard']+'}\nset ext_dump_objects {'+' '.join(c['ext_dump_objects'])+'}\n')


def command(stage, out):
    configuration(stage)
    return [value.replace('qbs_affine_slot0_aux_external_reset', 'qbs_affine_slot15_aux_external_reset')
            for value in old.command(stage, out)]


def prepare(out):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh one-shot output')
    pre = life.read_bound(PRE/'preflight-manifest.json', PRE_SHA)
    require(pre['status'] == 'AFFINE_FULL8_HOST_ELF_PREFLIGHT_NOT_DUT' and
            (pre['host_checks'],pre['host_negative_tests'],pre['commands'],pre['full_vrf_words'],
             pre['source_guard_bytes'],pre['csr_words'],pre['weight_profile'],pre['m'],pre['n'],pre['k_blocks']) ==
            (44,42,2,2048,7840,24,1,8,8,1), 'Exact same-ELF affine preflight required')
    plan = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(plan['simv'] == str(life.IMAGE) and len(plan['image']) == 66, 'Frozen66 image')
    book = life.read_bound(BASE/'admission-manifest.json', BASE_SHA)
    require(book['schema'] == 'QBS_AFFINE_SERIAL_AFTER758_NATIVE_ADMISSION_V1' and
            book['output'] == str(BASE), 'Not formal760')
    bitpath = BASE/'combined-bits.json'
    bits = life.read_bound(bitpath, book['output_pins'][str(bitpath)])
    row = bits['metrics']['fsm'][SCOPE]
    require(len(bits['tests']) == len(set(bits['tests'])) == 760 and
            (row['width'],row['checksum']) == (288,'3794445597') and
            not int(row['bits'],16) & (1 << (287-279)), 'Exact slot15 raw279 must still be zero')
    pins = life.merge_pins(pre['input_pins'], pre['output_pins'])
    pins = life.merge_pins(pins, plan['image'])
    for path, sha in ((PRE/'preflight-manifest.json',PRE_SHA),
                      (BASE/'admission-manifest.json',BASE_SHA),(bitpath,book['output_pins'][str(bitpath)]),
                      (life.PLAN,life.PLAN_SEAL),(focused.DOC,focused.DOC_SHA),
                      (focused.CONVERTER,focused.CONVERTER_SHA)):
        pins = life.merge_pins(pins,{str(path):sha})
    for path in (old.shared.DRIVER,old.shared.DRIVER_TEST,Path(old.__file__),Path(life.__file__),
                 Path(__file__).resolve(),HERE/'test_run_qbs_affine_aux_slot15.py'):
        pins = life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins)
    sel, entry = (out.with_name(out.name+suffix) for suffix in ('.selection.tcl','.entry.tcl'))
    with sel.open('x') as stream: stream.write(selection('aux'))
    with entry.open('x') as stream:
        stream.write('if {[file exists external-reset-selection.tcl]} {error "Existing reset selection"}\n'+
                     'file copy {'+str(sel)+'} external-reset-selection.tcl\nsource {'+str(old.shared.DRIVER)+'}\n')
    pins = life.merge_pins(pins,{str(path):life.digest(path) for path in (sel,entry)})
    record = dict(case='qbs_affine_slot15_aux',command=command('aux',out),pins=pins,timeout_s=600,
        selection=configuration('aux'),selection_source=str(sel),selection_sha256=life.digest(sel),
        preflight_seal=PRE_SHA,baseline_seal=BASE_SHA,raw_target=dict(scope=SCOPE,checksum=3794445597,
        width=288,index=279,before_hit=False),reset_pin='ara_tb.rst_n',reset_cycles=4,
        wave_byte_limit=64*1024*1024,coverage_admitted=False,native_oracle_qualified=False,
        full_scalar_qualified=False,parent_owned_shared_driver=True,no_automatic_AXI_reset=True,
        complete_pre_reset_slots_required=16,guard_projection_bit=15)
    path = out.with_name(out.name+'.prepared.json')
    life.save(path,record)
    print('SLOT15_PREPARED',path,life.digest(path),flush=True)


def backend():
    ns = dict(vars(old), configuration=configuration,selection=selection,command=command,
              BASE=BASE,BASE_SHA=BASE_SHA,STAGES=STAGES)
    for name in ('markers','run'):
        ns[name] = FunctionType(getattr(old,name).__code__,ns,name)
    return SimpleNamespace(**ns)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('prepare','run'))
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seal')
    a = p.parse_args()
    if a.mode == 'prepare': prepare(a.output.resolve())
    else:
        require(a.seal,'Exact prepared seal')
        backend().run('aux',a.output.resolve(),a.seal)
