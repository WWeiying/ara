"""Seal completed reference and assess fixed three-hour DUT budget; never launch."""
import sys
sys.dont_write_bytecode = True
from prepare import HERE, read, save, sha, require

root = HERE/'rvv_matrix_e64_m1'
ref = root/'reference01'
b = read(HERE/'bound02.json')
require(sha(HERE/'bound02.json') == 'df035f20627d9349144d3c7e255252234d519670bd99db4cbc4cfcb588c65adf', 'Bound drift')
for path, digest in b['pins'].items():
    require(sha(path) == digest, 'Input drift '+path)
execution, audit = read(ref/'execution.json'), read(ref/'audit_process_exit.json')
report, proof = read(ref/'reference.json'), read(root/'sourceproof.json')
require(execution['returncode'] == audit['returncode'] == 0 and not execution['timeout'] and
        not audit['timeout'] and execution['elapsed_s'] <= 120 and audit['elapsed_s'] <= 600,
        'Actual bounded reference/audit wait0 required')
require(not (ref/'not_completed.json').exists() and report['status'] == 'FULL_ORIGINAL_REFERENCE_PASS_NOT_DUT'
        and report['source_full_order'] and not report['partitioned'] and report['full_raw_parses'] == 1
        and [report[k] for k in ('calls','results','guards','vstart_checks','helper_instructions')] ==
        [5985,95760,11970,5985,77805], 'Exact full reference scope')
old = HERE.parent/'full_e64_m1_prepare01'
shape = 'rvv_matrix_e64_m1'
for name in ('case.c','main.c','model.json','original/scenario.S','original/operations.h','original/reconstructed_oracle.c'):
    require(sha(old/shape/name) == sha(root/name), 'Only compiler flag may change source: '+name)
for name in ('startup.S','runtime.c','replay.ld'):
    require(sha(old/'runtime'/name) == sha(HERE/'runtime'/name), 'Runtime source drift')
for backend in ('soc','spike'):
    previous = read(old/shape/backend/'compile.log.command.json')['command']
    current = read(root/backend/'compile.log.command.json')['command']
    require([x.replace(str(old),str(HERE)).replace('-Os','-O2') for x in previous] == current,
            'Only approved -Os to -O2 flag change')
pins = dict(b['pins'])
for path in (old/'READY.json',old/shape/'sourceproof.json',old/shape/'reference01/reference.json'):
    pins[str(path)] = sha(path)
pins[str(HERE/'bound02.json')] = sha(HERE/'bound02.json')
for path in ref.iterdir():
    if path.name == 'commits.log':
        require(path.stat().st_size == report['raw_bytes'] == execution['raw_bytes'], 'Raw size')
        pins[str(path)] = report['raw_sha256']
    elif path.is_file():
        pins[str(path)] = sha(path)

measured = []
for shape, expected_firmware, expected_seconds in (
        ('e32_mf2', 5922683, 10026.130593086127),
        ('e16_mf4', 3806624, 6406.345964943059)):
    work = HERE.parent/f'full_{shape}_vcs_m6_plan01/prepared01'
    audit_root = HERE.parent/f'full_{shape}_terminal_audit01/run01'
    terminal = read(audit_root/'TERMINAL.json')
    outcome = read(audit_root/'audit_process_exit.json')
    candidate = read(audit_root/'candidate_report.json')
    complete = read(work/'complete.json')
    require(sha(audit_root/'candidate_report.json') == terminal['report_sha256'] and
            sha(audit_root/'audit_process_exit.json') == terminal['actual_audit_exit_sha256'] and
            sha(work/'complete.json') == candidate['complete_sha256'] and
            outcome['returncode'] == 0 and not outcome['timed_out'] and not outcome['error'], 'Measured receipt chain')
    result = complete['results'][0]
    detail = audit_root/f'arithmetic_full_{shape}.json'
    require(sha(detail) == candidate['reports'][0]['report_sha256'], 'Measured full report')
    strict = read(detail)['strict']
    require(result['returncode'] == 0 and result['elapsed_s'] == expected_seconds and
            strict['firmware_through_ctrl'] == expected_firmware, 'Measured baseline differs')
    for p in (audit_root/'TERMINAL.json', audit_root/'audit_process_exit.json',
              audit_root/'candidate_report.json', work/'complete.json', detail):
        pins[str(p)] = sha(p)
    rate = expected_firmware/expected_seconds
    nominal = report['firmware_through_htif']/rate
    measured.append(dict(shape=shape,firmware=expected_firmware,seconds=expected_seconds,
                         retires_per_second=rate,projected_e64_s=nominal,
                         projected_e64_with20percent_s=nominal*1.2))
projection = max(x['projected_e64_with20percent_s'] for x in measured)
pins[str(HERE/'seal_cost.py')] = sha(HERE/'seal_cost.py')
ready = dict(status='FULL_ORIGINAL_E64_M1_REFERENCE_PASS_NOT_DUT',
    shape='rvv_matrix_e64_m1',optimization='Only -Os to -O2; no autovector',source_C_text_recovered=False,binary_equivalent_original_reconstruction=True,
    original_linux_sha256=proof['original_sha256'],soc_sha256=proof['backends']['soc']['sha256'],
    spike_sha256=proof['backends']['spike']['sha256'],calls=5985,results=95760,guards=11970,
    helper_instructions=77805,vstart_checks=5985,operations=35,seeds=3,capacity=16,physical_mask_bytes=128,
    reference_report_sha256=sha(ref/'reference.json'),firmware_through_htif=report['firmware_through_htif'],
    actual_reference_exit=execution,actual_audit_exit=audit,host_positive=1,host_negative=9,
    fflags_oracle='Original has no explicit fflags oracle; no invented acceptance',
    evidence_pins=pins,cost=dict(measured_baselines=measured,margin=0.2,simulator_limit_s=10800,
    conservative_projection_s=projection,budget_gate='FIT_PROJECTION_ONLY' if projection<=10800 else 'BLOCKED_OVER_3H',
    no_timeout_extension=True,not_measured_M7_e64_runtime=True,completion_guaranteed=False),
    DUT_runs=0,new_image_builds=0,raw_parses=1)
save(HERE/'READY.json',ready)
print('READY_SHA',sha(HERE/'READY.json'),'FIRMWARE',report['firmware_through_htif'],
      'BUDGET',ready['cost'],flush=True)
