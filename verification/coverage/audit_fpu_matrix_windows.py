"""Convert existing eleven focused waves and audit reset windows, no simulations."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import run_fpu_external_reset_matrix as matrix
import audit_external_reset_window as window

life, require = matrix.life, matrix.require
SEAL = '9e0c4ba9545639916c33b79ccf2a0990e85d496fc76866abba96f7f1d5d7b5dd'
OUT = life.OUT / 'fpu-matrix-window-audit-parent-20261007-01'


def one(record):
    root = Path(record['output'])
    terminal = root / 'simulation-status.json'
    status = json.loads(terminal.read_bytes())
    require(status['returncode'] == 0 and status['status'] == 'SIMULATION_EXITED_NOT_ADMITTED',
            'Successful terminal required')
    manifest = root / 'manifest.json'
    executed = json.loads(manifest.read_bytes())
    require(executed['selection'] == record['selection'] and
            executed['command'] == record['command'], 'Executed case identity differs')
    vpd, vcd = root / 'external-reset.vpd', root / 'external-reset.vcd'
    require(vpd.is_file() and 0 < vpd.stat().st_size <= record['wave_byte_limit'],
            'Invalid bounded waveform')
    require(not vcd.exists(), 'No ambiguous prior conversion')
    pins = {str(p): life.digest(p) for p in (terminal, manifest, vpd)}
    converter = matrix.shared.focused.CONVERTER
    command = [str(converter), '+splitpacked', str(vpd), str(vcd)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    log = OUT / (record['case'] + '.conversion.log')
    with log.open('x') as stream:
        stream.write(result.stdout + result.stderr)
    require(result.returncode == 0 and vcd.is_file() and vcd.stat().st_size > 0,
            'Official waveform conversion failed')
    checked = window.audit(vcd, record['selection'])
    life.check(pins)
    checked.update(case=record['case'], output=str(root), command=command,
                   pins=life.merge_pins(pins, {str(vcd): life.digest(vcd), str(log): life.digest(log)}))
    life.save(OUT / (record['case'] + '.json'), checked)
    return checked


def main():
    require(not OUT.exists(), 'Fresh independent audit only')
    plan = life.read_bound(matrix.PLAN, SEAL)
    require(plan['schema'] == 'FPU_SHARED_EXTERNAL_RESET_REMAINING11_V1' and
            [(r['sew'], r['stage']) for r in plan['cases']] == matrix.CASES,
            'Exact eleven-case matrix required')
    life.check(plan['pins'])
    converter = matrix.shared.focused.CONVERTER
    require(life.digest(converter) == matrix.shared.focused.CONVERTER_SHA,
            'Official converter differs')
    terminal = matrix.PLAN.with_name(matrix.PLAN.name + '.terminal.json')
    results = json.loads(terminal.read_bytes())
    require(results['plan_seal'] == SEAL and len(results['cases']) == 11 and
            {r['case'] for r in results['cases']} == {r['case'] for r in plan['cases']} and
            all(r['status'] == 'TERMINAL_CAPTURE_PENDING_ARCHITECTURE_QUALIFICATION'
                for r in results['cases']), 'Incomplete matrix terminal')
    OUT.mkdir()
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            audited = list(pool.map(one, plan['cases']))
        pins = {str(p): life.digest(p) for p in (
            matrix.PLAN, terminal, converter, Path(__file__).resolve(), Path(window.__file__).resolve(),
            Path(window.__file__).with_name('test_audit_external_reset_window.py'))}
        for case in audited:
            pins = life.merge_pins(pins, case['pins'])
        life.check(plan['pins'])
        life.check(pins)
        life.save(OUT / 'result.json', dict(status='ELEVEN_ACTUAL_STATE_RESET_WINDOWS_PASS_ONLY',
            cases=audited, pins=pins, full_architecture_checked=False, coverage_admitted=False,
            simulator_rerun=False, rtl_changed=False))
        print('ELEVEN_ACTUAL_STATE_RESET_WINDOWS_PASS_ONLY', flush=True)
    except Exception as error:
        life.save(OUT / 'failure.json', dict(reason=str(error), coverage_admitted=False))
        raise


if __name__ == '__main__':
    main()
