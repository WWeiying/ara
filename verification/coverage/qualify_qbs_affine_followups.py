"""Source-complete terminal qualification only; historical746 delta is not admission."""
import argparse
from pathlib import Path
from types import FunctionType, SimpleNamespace

import recheck_qbs_affine_native_dependencies as closure

q = closure.q
CASES = {
    'scale': ('qbs-affine-scale-external-reset-old-image-agent-20261007-01',
              '7f3303074434eb05ddb030bc4a1f558f2bddaf161a3f05b732581d8ad0f204fa'),
    'min_scale': ('qbs-affine-min-scale-external-reset-old-image-agent-20261007-01',
                  '1c6b5c8f35f77ddc18942507678b14e87965f50d6039c0a05f64a1d1d226a7d1'),
}


def collect(stage, output):
    old = q.life
    dependencies = closure.source_pins()
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_qualify_qbs_affine_followups.py')):
        dependencies[str(path)] = old.digest(path)

    def check(pins):
        return old.check(old.merge_pins(pins, dependencies))

    def save(path, value):
        if path.name == 'evidence-pins.json':
            value = old.merge_pins(value, dependencies)
        old.save(path, value)

    life = SimpleNamespace(**dict(vars(old), check=check, save=save))
    name, seal = CASES[stage]
    FunctionType(q.collect.__code__, dict(q.collect.__globals__, life=life))(
        stage, old.OUT / name, seal, output)
    check(dependencies)
    result_path = output / 'qualification.json'
    result = old.read_bound(result_path, old.digest(result_path))
    q.require(result['baseline'] == 746 and result['stage'] == stage and
              result['coverage_admitted'] is False and
              result['reset_stage_and_slot_reuse_wave_verified'] is True,
              'Unexpected qualification scope')
    old.save(output / 'admission-hold.json', dict(
        status='QUALIFIED_FOLLOWUP_WAITING_FOR_DESCARTES_FINAL_BASE_NOT_ADMITTED',
        qualification_sha256=old.digest(result_path), historical_diagnostic_baseline=746,
        latest_population_claimed=False, admission_performed=False,
        final_admission_requires_fresh_latest_prefix_and_OR=True))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage', choices=CASES, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    collect(a.stage, a.output.resolve())
