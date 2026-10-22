"""One frozen 600-second matrix4 simulation; never functional admission."""
import argparse
import json
from pathlib import Path
import run_qbs_payload_phase763 as prior

life, reused = prior.life, prior.reused
PRE = life.OUT / 'qbs-payload-matrix4-preflight764-agent-20261007-02'
SEAL = '04d9e8a86a035f4d30c4f100fea82a80def3f0154c4260e45a4891783f1b700e'
NAME = 'qbs_payload_matrix4'
ELF_SHA = '69d39fb545a28b4a452f215d5349cf033a2e271a11d8678e2b6c3f4dfcd4a924'


def validate(pre):
    reused.exact(pre, dict(status='MATRIX4_HOST_NATIVE_STATIC_ELF_READY_NOT_DUT_PASS',
        binary=str(PRE / (NAME + '.elf')), binary_sha256=ELF_SHA, baseline=764,
        commands=4, budget_s=600, host_checks=28, host_negative_tests=24,
        dut_checks=24, full_vrf_bytes=16384, source_readback_bytes=18176,
        csr_values=48, wp=[14,6,10,2], ap=[8,12,8,8],
        coverage_admitted=False, vcs_launched=False, full_scalar_ISA_verified=False),
        'Matrix preflight')
    if len(pre['sites']) != 4 or any(s['word'] != 0x0eb5045b for s in pre['sites']):
        raise ValueError('Exact four M8 custom sites required')
    if len({s['pc'] for s in pre['sites']}) != 4:
        raise ValueError('Duplicate custom PC')


def prepare(output):
    output = Path(output).absolute()
    if output.parent != life.OUT or output.resolve() != output or output.exists():
        raise ValueError('Fresh output required')
    pre = life.read_bound(PRE / 'preflight-manifest.json', SEAL)
    validate(pre)
    plan = life.read_bound(life.PLAN, life.PLAN_SEAL)
    if len(plan['image']) != 66 or plan['image'].get(str(life.IMAGE)) != reused.IMAGE_SEAL:
        raise ValueError('Frozen image66 differs')
    pins = life.merge_pins(pre['input_pins'], pre['output_pins'])
    pins = life.merge_pins(pins, plan['image'])
    pins = life.merge_pins(pins, {str(PRE/'preflight-manifest.json'):SEAL,
                                str(life.PLAN):life.PLAN_SEAL})
    for path in (Path(__file__), Path(__file__).with_name('test_run_qbs_payload_matrix4.py'),
                 Path(prior.__file__), Path(prior.full8.__file__),
                 Path(reused.__file__), Path(life.__file__)):
        pins = life.merge_pins(pins, {str(path.resolve()):life.digest(path)})
    if life.digest(Path(life.__file__)) != reused.LIFE_SEAL:
        raise ValueError('Lifecycle drift')
    life.check(pins)
    reused.NAME = NAME
    reused.ELF = PRE / (NAME + '.elf')
    reused.ELF_SEAL = ELF_SHA
    return output, dict(case=NAME, preflight=pre, pins=pins,
        command=reused.command(output), timeout_s=600, old_image_files_checked=66,
        coverage_admitted=False, automatic_retry=False,
        simulator_exit_is_not_functional_pass=True,
        eventual_admission_base_required=765,
        qualification_required='Independent native256bytes/job, full VRF4096bytes/job, all CSR/guards/source readbacks and exact lifecycle; no full scalar ISA claim',
        prediction_is_not_measured_gain=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare','run'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--prepared-seal')
    a = p.parse_args()
    if bool(a.prepared_seal) != (a.mode == 'run'):
        p.error('Run requires prepared seal')
    out, record = prepare(a.output)
    path = out.with_name(out.name + '.prepared.json')
    if a.mode == 'prepare':
        if path.exists():
            raise ValueError('Preserve existing preparation')
        life.save(path, record)
        print(json.dumps(dict(prepared=str(path), seal=life.digest(path), pins=len(record['pins']))), flush=True)
    else:
        if life.read_bound(path, a.prepared_seal) != record:
            raise ValueError('Prepared drift')
        reused.run(out, record)


if __name__ == '__main__':
    main()
