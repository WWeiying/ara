"""Three exact slot0 stage selections; one-shot shared-driver old-image measurements."""
import argparse
import json
from pathlib import Path

import run_gap95_simulation as life
import run_gap115_axi_capture as focused
import run_external_reset_fixture as shared

HERE = Path(__file__).resolve().parent
PRE = life.OUT / 'qbs-affine-slot0-preflight-agent-20261007-01'
PRE_SHA = '061de2693c316663f5c6de2bc7f4f0a92a6b569530fdfc8ee8626e2a2b0b54ca'
BASE = life.OUT / 'gap115-offline-admitted-745-agent-20261007-01'
BASE_SHA = '965ec298fcd169b9a184367893ddfad7b080c75ac71e85fad72fe4977cf7b5b6'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine.i_compute_engine.i_fp_accumulator'
STAGES = {'aux': (1, 9), 'scale': (2, 16), 'min_scale': (3, 14)}
require = shared.require


def configuration(stage):
    require(stage in STAGES, 'Unknown QBS stage')
    ara = 'ara_tb.dut.i_ara_soc.i_system.i_ara'
    target, guard = SCOPE + '.entry_state_q[0]', SCOPE + '.entry_valid_q[0]'
    return dict(ext_target=target, ext_value=STAGES[stage][0], ext_guard=guard,
        ext_dump_objects=['ara_tb.clk', 'ara_tb.rst_n', ara + '.axi_req_o', ara + '.axi_resp_i',
                          target, guard, SCOPE + '.entry_inflight_q[0]'])


def selection(stage):
    c = configuration(stage)
    return ('set ext_target {' + c['ext_target'] + '}\nset ext_value ' + str(c['ext_value']) +
            '\nset ext_guard {' + c['ext_guard'] + '}\nset ext_dump_objects {' +
            ' '.join(c['ext_dump_objects']) + '}\n')


def command(stage, out):
    require(stage in STAGES, 'Unknown QBS stage')
    name = 'qbs_affine_slot0_' + stage + '_external_reset'
    return [str(life.IMAGE), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
        '+PRELOAD=' + str(PRE / 'qbs_affine_slot0_cancel.elf'), '+TESTCASE=' + name,
        '+COMMIT_TOHOST=80001000', '+COMMIT_TRACE=' + str(out / 'commit_trace.csv'),
        '+VECTOR_TRACE=' + str(out / 'vector_trace.csv'), '-cm', 'line+cond+fsm+tgl+branch',
        '-cm_dir', str(out / 'code.vdb'), '-cm_name', name, '+ARA_UVM_TRACE_LIMIT=100000',
        '+ARA_CONTRACT_TRACE_LIMIT=100000', '-ucli', '-do', str(out.with_name(out.name + '.entry.tcl'))]


def prepare(stage, out):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh direct output required')
    pre = life.read_bound(PRE / 'preflight-manifest.json', PRE_SHA)
    require(pre['status'] == 'AFFINE_FULL8_HOST_ELF_PREFLIGHT_NOT_DUT' and
            pre['host_checks'] == 44 and pre['host_negative_tests'] == 42 and pre['commands'] == 2 and
            pre['full_vrf_words'] == 2048 and pre['source_guard_bytes'] == 7840 and pre['csr_words'] == 24 and
            pre['weight_profile'] == 1 and (pre['m'], pre['n'], pre['k_blocks']) == (8, 8, 1),
            'Exact affine preflight differs')
    plan = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(plan['simv'] == str(life.IMAGE) and len(plan['image']) == 66, 'Frozen66 image required')
    book = life.read_bound(BASE / 'admission-manifest.json', BASE_SHA)
    require(book['schema'] == 'GAP115_INDEPENDENT_AXI745_ADMISSION_V1', 'Not formal745')
    bitpath = BASE / 'combined-bits.json'
    bits = life.read_bound(bitpath, book['output_pins'][str(bitpath)])
    shape = bits['metrics']['fsm'][SCOPE]
    code, index = STAGES[stage]
    require(shape['width'] == 288 and str(shape['checksum']) == '3794445597' and
            not (int(shape['bits'], 16) & (1 << (287 - index))), 'Target checksum/width/zero differs')
    pins = life.merge_pins(pre['input_pins'], pre['output_pins'])
    pins = life.merge_pins(pins, plan['image'])
    for p, sha in [(PRE / 'preflight-manifest.json', PRE_SHA), (BASE / 'admission-manifest.json', BASE_SHA),
                   (bitpath, book['output_pins'][str(bitpath)]), (life.PLAN, life.PLAN_SEAL),
                   (focused.DOC, focused.DOC_SHA), (focused.CONVERTER, focused.CONVERTER_SHA)]:
        pins = life.merge_pins(pins, {str(p): sha})
    for p in [shared.DRIVER, shared.DRIVER_TEST, Path(__file__).resolve(),
              HERE / 'test_run_qbs_affine_external_reset.py', Path(life.__file__).resolve()]:
        pins = life.merge_pins(pins, {str(p): life.digest(p)})
    life.check(pins)
    sel = out.with_name(out.name + '.selection.tcl')
    entry = out.with_name(out.name + '.entry.tcl')
    with sel.open('x') as stream:
        stream.write(selection(stage))
    with entry.open('x') as stream:
        stream.write('if {[file exists external-reset-selection.tcl]} {error "Existing reset selection"}\n' +
                     'file copy {' + str(sel) + '} external-reset-selection.tcl\nsource {' + str(shared.DRIVER) + '}\n')
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in (sel, entry)})
    record = dict(case='qbs_affine_slot0_' + stage, command=command(stage, out), pins=pins, timeout_s=600,
        selection=configuration(stage), selection_source=str(sel), selection_sha256=life.digest(sel),
        preflight_seal=PRE_SHA, baseline_seal=BASE_SHA, raw_target=dict(scope=SCOPE, checksum=3794445597,
        width=288, index=index, before_hit=False), reset_pin='ara_tb.rst_n', reset_cycles=4,
        wave_byte_limit=64 * 1024 * 1024, coverage_admitted=False, native_oracle_qualified=False,
        full_scalar_qualified=False, parent_owned_shared_driver=True, no_automatic_AXI_reset=True)
    path = out.with_name(out.name + '.prepared.json')
    life.save(path, record)
    print(json.dumps(dict(prepared=str(path), seal=life.digest(path), stage=stage, VCS_started=False)), flush=True)


def markers(text, stage):
    c = configuration(stage)
    expected = ['EXT_RESET_READY %s %d' % (c['ext_target'], c['ext_value']),
                'EXT_RESET_TARGET %s %d' % (c['ext_target'], c['ext_value']), 'EXT_RESET_ASSERT']
    expected += ['EXT_RESET_LOW_EDGE %d' % edge for edge in range(1, 5)]
    expected += ['EXT_RESET_RELEASE', 'EXT_RESET_DONE']
    actual = [line for line in text.splitlines() if line.startswith('EXT_RESET_')]
    require(actual == expected, 'Missing/duplicate/error/reset stage markers; echo is not evidence')
    return actual


def run(stage, out, seal):
    path = out.with_name(out.name + '.prepared.json')
    record = life.read_bound(path, seal)
    require(record['command'] == command(stage, out) and record['selection'] == configuration(stage) and
            record['timeout_s'] == 600 and record['preflight_seal'] == PRE_SHA and
            record['baseline_seal'] == BASE_SHA, 'Prepared runtime identity differs')
    record['pins'] = life.merge_pins(record['pins'], {str(path): seal})
    require(not out.exists(), 'One-shot run; no retry/overwrite')
    try:
        life.run(out, record)
        actual = markers((out / 'console.log').read_text(), stage)
        require(life.digest(out / 'external-reset-selection.tcl') == record['selection_sha256'],
                'Executed cwd selection differs')
        wave = out / 'external-reset.vpd'
        require(wave.is_file() and 0 < wave.stat().st_size <= record['wave_byte_limit'], 'Focused waveform bound')
        life.save(out / 'reset-capture.json', dict(status='EXACT_RESET_MARKERS_PENDING_WAVE_AND_ARCHITECTURE',
            stage=stage, markers=actual, wave_sha256=life.digest(wave), coverage_admitted=False,
            additional_routes_authorized=False))
    except Exception as exc:
        if out.exists():
            life.save(out / 'reset-capture-failure.json', dict(reason=str(exc), coverage_admitted=False))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'run'))
    parser.add_argument('--stage', choices=STAGES, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare(args.stage, args.output.resolve())
    else:
        require(args.seal, 'Exact prepared seal required')
        run(args.stage, args.output.resolve(), args.seal)
